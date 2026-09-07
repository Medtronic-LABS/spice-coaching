"""CLI entry point for RAG retrieval and chatbot evaluation."""

from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

from platform_service.integrations.ai_runtime_client import AIRuntimeClient

from eval.rag.answer_metrics import aggregate_e2e_summaries
from eval.rag.bm25 import Bm25Index, build_card_indexes
from eval.rag.card_embedding import CardEmbeddingRetriever
from eval.rag.checkpoint import (
    ArtifactKind,
    CheckpointContext,
    CorpusCounts,
    EvalRunConfig,
    SkipKind,
    after_record,
    checkpoint_path,
    delete_checkpoint,
    ensure_resume_policy,
    init_progress,
)
from eval.rag.corpus import (
    build_module_card_corpus,
    corpus_docs_from_modules,
    count_embedded_published_modules,
    count_local_embedded_published_cards,
    load_cards_by_module_ids,
    load_published_corpus,
    load_published_modules,
)
from eval.rag.dataset import (
    collect_golden_resolution_issues,
    load_golden_dataset,
    resolve_golden_labels,
    unresolvable_golden_record_ids,
)
from eval.rag.embedding import EmbeddingRetriever
from eval.rag.generation_batch import (
    GenerationBatchConfig,
    build_generation_batch_report,
    run_bm25_generation_batch,
    run_embedding_generation_batch,
)
from eval.rag.golden_coverage import build_coverage_report, write_coverage_report
from eval.rag.golden_manifest import compile_manifest, load_golden_source_array
from eval.rag.golden_schema import (
    validate_golden_card_module_alignment,
    validate_golden_corpus_alignment,
    validate_golden_dataset,
)
from eval.rag.judge_stage import judge_report_file, write_report_payload
from eval.rag.llm_judge import LlmJudge
from eval.rag.rag_dataset import (
    load_rag_golden_dataset,
    validate_expected_card_ids,
    validate_expected_module_ids,
)
from eval.rag.rag_runner import RagQueryRunner, rag_result_to_artifact_dict
from eval.rag.report import (
    artifact_from_bm25_hits,
    artifact_from_card_embedding_hits,
    artifact_from_embedding_hits,
    artifact_from_pipeline_hits_with_lookup,
    build_batch_report,
    build_rag_batch_report,
    write_batch_report,
    write_rag_batch_report,
)
from eval.rag.tenant_scope import eval_tenant_scope

_TOOL_COMMANDS = frozenset({"validate", "coverage", "golden-compile", "judge"})


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate retrieval over published modules in the database.",
    )
    parser.add_argument(
        "query",
        nargs="?",
        help="Search query (omit to run batch eval against --dataset)",
    )
    parser.add_argument(
        "--method",
        choices=["bm25", "embedding", "local_embedding", "card_local_embedding", "rag", "local_rag"],
        default="bm25",
        help=(
            "Evaluation method: bm25, embedding, local_embedding, "
            "card_local_embedding, rag, or local_rag (default: bm25)"
        ),
    )
    parser.add_argument("--k", type=int, default=5, help="Top-K results (default: 5)")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/rag/golden/golden_dataset.json"),
        help="Golden JSON dataset for batch retrieval eval (default: eval/rag/golden/golden_dataset.json)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Batch JSON report path (default: eval/rag/reports/<method>-run.json)",
    )
    parser.add_argument(
        "--tenant-id", type=int, default=None, help="Tenant bigint scope (required for multi-tenant corpora)"
    )
    parser.add_argument(
        "--language",
        choices=["en", "bn"],
        default="bn",
        help="Canonical dataset language: question_en/expected_answer_en or question_bn/expected_answer_bn (default: bn)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Batch run identifier (default: <method>-YYYYMMDD-HHMMSS)",
    )
    parser.add_argument(
        "--ai-runtime-url",
        default="http://localhost:8000/",
        help="ai-runtime base URL override (default: platform AI_RUNTIME_BASE_URL)",
    )
    parser.add_argument(
        "--ai-runtime-token",
        default="dev-internal-token",
        help="ai-runtime internal token override (default: platform AI_RUNTIME_TOKEN)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="RAG/local_rag batch only: evaluate at most N records (default: all)",
    )
    parser.add_argument(
        "--record-id",
        default=None,
        help="RAG/local_rag batch only: evaluate a single record id",
    )
    parser.add_argument(
        "--generate",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "BM25/embedding batch only: retrieve then generate LLM answers "
            "(writes a generation report suitable for the judge subcommand)"
        ),
    )
    parser.add_argument(
        "--llm-judge",
        action=argparse.BooleanOptionalAction,
        default=False,
        help=(
            "RAG/local_rag batch only: run LLM-as-judge inline after generation (default: off; "
            "use `rag-eval judge` to score saved reports from any method)"
        ),
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from checkpoint beside --output",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=10,
        help="Save checkpoint every N records processed (0 = disable; default: 10)",
    )
    return parser.parse_args(argv)


def _parse_tool_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Golden dataset tooling.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate golden dataset schema and UUIDs")
    validate_parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/rag/golden/Golden_Dataset.manifest.json"),
        help="Golden dataset path or manifest",
    )
    validate_parser.add_argument("--tenant-id", type=int, default=None)

    coverage_parser = subparsers.add_parser("coverage", help="Report golden dataset coverage gaps")
    coverage_parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("eval/rag/golden/Golden_Dataset.manifest.json"),
        help="Golden dataset path or manifest",
    )
    coverage_parser.add_argument(
        "--output",
        type=Path,
        default=Path("eval/rag/reports/golden-coverage.json"),
    )
    coverage_parser.add_argument("--tenant-id", type=int, default=None)
    coverage_parser.add_argument("--min-records-per-module", type=int, default=4)

    compile_parser = subparsers.add_parser(
        "golden-compile",
        help="Merge manifest shards into compiled Golden_Dataset.json",
    )
    compile_parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("eval/rag/golden/Golden_Dataset.manifest.json"),
    )
    compile_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Override compiled output path",
    )

    judge_parser = subparsers.add_parser(
        "judge",
        help="Run LLM-as-judge on a saved RAG or retrieval+generation report",
    )
    judge_parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input JSON report with generated answers (rag-run.json, bm25-gen-run.json, etc.)",
    )
    judge_parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output JSON path (default: <input-stem>-judged.json beside input)",
    )
    judge_parser.add_argument("--tenant-id", type=int, default=None)
    judge_parser.add_argument(
        "--ai-runtime-url",
        default="http://localhost:8000/",
        help="ai-runtime base URL override",
    )
    judge_parser.add_argument(
        "--ai-runtime-token",
        default="dev-internal-token",
        help="ai-runtime internal token override",
    )

    return parser.parse_args(argv)


def _parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    if args_list and args_list[0] in _TOOL_COMMANDS:
        tool_args = _parse_tool_args(args_list)
        tool_args.mode = "tool"
        return tool_args
    eval_args = _parse_args(args_list)
    eval_args.mode = "eval"
    return eval_args


def _apply_method_defaults(args: argparse.Namespace) -> None:
    if args.output is None:
        if getattr(args, "generate", False) and args.method in {"bm25", "embedding"}:
            args.output = Path(f"eval/rag/reports/{args.method}-gen-run.json")
        else:
            args.output = Path(f"eval/rag/reports/{args.method}-run.json")


def _print_bm25_hits(*, query: str, corpus_count: int, hits: list) -> None:
    print(f"Corpus: {corpus_count} published modules")
    print(f'Query: "{query}"')
    print()
    print(f"{'rank':>4}  {'module_id':<36}  {'bm25_score':>10}  title_en")
    for hit in hits:
        title = hit.primary_title or hit.title_en or hit.title_bn or ""
        print(f"{hit.rank:>4}  {str(hit.module_id):<36}  {hit.bm25_score:>10.4f}  {title}")


def _print_embedding_hits(*, query: str, embedded_count: int, hits: list) -> None:
    print(f"Corpus: {embedded_count} embedded published modules")
    print(f'Query: "{query}"')
    print()
    print(f"{'rank':>4}  {'module_id':<36}  {'cosine_dist':>10}  title_en")
    for hit in hits:
        title = hit.primary_title or hit.title_en or hit.title_bn or ""
        print(f"{hit.rank:>4}  {str(hit.module_id):<36}  {hit.cosine_distance:>10.4f}  {title}")


def _print_card_embedding_hits(*, query: str, embedded_count: int, hits: list) -> None:
    print(f"Corpus: {embedded_count} embedded published cards")
    print(f'Query: "{query}"')
    print()
    print(f"{'rank':>4}  {'card_id':<36}  {'module_id':<36}  {'cosine_dist':>10}  title")
    for hit in hits:
        title = hit.primary_title or hit.title_en or hit.title_bn or ""
        print(
            f"{hit.rank:>4}  {str(hit.card_id):<36}  {str(hit.module_id):<36}  "
            f"{hit.cosine_distance:>10.4f}  {title}"
        )


def _record_has_card_eval(record) -> bool:
    if record.expected_module_id is None:
        return False
    return bool(record.expected_card_ids)


def _eval_run_config(
    args: argparse.Namespace,
    method: str,
    *,
    local_card: bool = False,
) -> EvalRunConfig:
    return EvalRunConfig(
        method=method,
        dataset_path=str(args.dataset),
        k=args.k,
        language=args.language,
        tenant_id=args.tenant_id,
        generate=args.generate,
        local_card=local_card,
        llm_judge=args.llm_judge,
    )


def _checkpoint_context(
    args: argparse.Namespace,
    config: EvalRunConfig,
    corpus_counts: CorpusCounts,
    artifact_kind: ArtifactKind,
) -> CheckpointContext:
    return CheckpointContext(
        output_path=args.output,
        interval=args.checkpoint_interval,
        config=config,
        corpus_counts=corpus_counts,
        artifact_kind=artifact_kind,
    )


async def _run_bm25_single_query(args: argparse.Namespace) -> int:
    if not args.query:
        print("error: query must not be empty", file=sys.stderr)
        return 2

    with eval_tenant_scope(args.tenant_id):
        docs = await load_published_corpus(tenant_id=args.tenant_id)
        index = Bm25Index(docs)
        hits = index.search(args.query, k=args.k)
    _print_bm25_hits(query=args.query, corpus_count=index.doc_count, hits=hits)
    return 0


async def _run_embedding_single_query(args: argparse.Namespace) -> int:
    if not args.query:
        print("error: query must not be empty", file=sys.stderr)
        return 2

    retriever = EmbeddingRetriever(
        tenant_id=args.tenant_id,
        base_url=args.ai_runtime_url,
        token=args.ai_runtime_token,
    )
    try:
        with eval_tenant_scope(args.tenant_id):
            embedded_count = await retriever.embedded_count()
            if embedded_count == 0:
                print(
                    "warning: no published modules have embeddings; run the embedding worker first",
                    file=sys.stderr,
                )
            hits = await retriever.search(args.query, k=args.k)
        _print_embedding_hits(query=args.query, embedded_count=embedded_count, hits=hits)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await retriever.aclose()
    return 0


async def _run_local_embedding_single_query(args: argparse.Namespace) -> int:
    if not args.query:
        print("error: query must not be empty", file=sys.stderr)
        return 2

    retriever = EmbeddingRetriever(
        tenant_id=args.tenant_id,
        base_url=args.ai_runtime_url,
        token=args.ai_runtime_token,
        use_local=True,
    )
    try:
        with eval_tenant_scope(args.tenant_id):
            embedded_count = await retriever.embedded_count()
            if embedded_count == 0:
                print(
                    "warning: no published modules have local embeddings; "
                    "run bin/backfill_module_local_embeddings.py first",
                    file=sys.stderr,
                )
            hits = await retriever.search(args.query, k=args.k)
        _print_embedding_hits(query=args.query, embedded_count=embedded_count, hits=hits)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await retriever.aclose()
    return 0


async def _run_card_local_embedding_single_query(args: argparse.Namespace) -> int:
    if not args.query:
        print("error: query must not be empty", file=sys.stderr)
        return 2

    retriever = CardEmbeddingRetriever(
        tenant_id=args.tenant_id,
        base_url=args.ai_runtime_url,
        token=args.ai_runtime_token,
    )
    try:
        with eval_tenant_scope(args.tenant_id):
            embedded_count = await retriever.embedded_count()
            if embedded_count == 0:
                print(
                    "warning: no published cards have local embeddings; "
                    "run bin/backfill_module_card_local_embeddings.py first",
                    file=sys.stderr,
                )
            hits = await retriever.search(args.query, k=args.k)
        _print_card_embedding_hits(query=args.query, embedded_count=embedded_count, hits=hits)
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await retriever.aclose()
    return 0


async def _run_bm25_generation_batch(args: argparse.Namespace) -> int:
    dataset_path = args.dataset
    try:
        records = load_rag_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ensure_resume_policy(args.output, args.resume)
    method = "bm25"
    config = _eval_run_config(args, method)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method}-gen-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="dict",
    )

    with eval_tenant_scope(args.tenant_id):
        modules = await load_published_modules(tenant_id=args.tenant_id)
        cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
        docs = corpus_docs_from_modules(modules, cards_by_module_raw)
        cards_by_module = build_module_card_corpus(modules, cards_by_module_raw)
        index = Bm25Index(docs)

        batch_config = GenerationBatchConfig(
            retrieval_method=method,
            dataset_path=dataset_path,
            k=args.k,
            tenant_id=args.tenant_id,
            ai_runtime_url=args.ai_runtime_url,
            ai_runtime_token=args.ai_runtime_token,
            run_id=progress.run_id,
        )
        corpus_counts = CorpusCounts(published=index.doc_count, embedded=None)
        checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "dict")
        await run_bm25_generation_batch(
            records=records,
            config=batch_config,
            index=index,
            modules=modules,
            cards_by_module=cards_by_module,
            progress=progress,
            checkpoint_ctx=checkpoint_ctx,
        )

    artifacts = progress.dict_artifacts()
    e2e_summary = aggregate_e2e_summaries(artifacts)
    report = build_generation_batch_report(
        config=batch_config,
        artifacts=artifacts,
        corpus_published_count=corpus_counts.published,
        corpus_embedded_count=None,
        e2e_summary=e2e_summary,
    )
    write_report_payload(report, args.output)
    delete_checkpoint(checkpoint_path(args.output))
    print(f"Wrote {args.output}")
    print(f"Evaluated {len(artifacts)} records with BM25 retrieval + LLM generation")
    print(f"Run `rag-eval judge --input {args.output}` to score answers")
    return 0


async def _run_embedding_generation_batch(args: argparse.Namespace) -> int:
    dataset_path = args.dataset
    try:
        records = load_rag_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ensure_resume_policy(args.output, args.resume)
    method = "embedding"
    config = _eval_run_config(args, method)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method}-gen-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="dict",
    )

    with eval_tenant_scope(args.tenant_id):
        modules = await load_published_modules(tenant_id=args.tenant_id)
        cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
        docs = await load_published_corpus(tenant_id=args.tenant_id)
        cards_by_module = build_module_card_corpus(modules, cards_by_module_raw)
        retriever = EmbeddingRetriever(
            tenant_id=args.tenant_id,
            base_url=args.ai_runtime_url,
            token=args.ai_runtime_token,
        )
        try:
            embedded_count = await retriever.embedded_count()
            batch_config = GenerationBatchConfig(
                retrieval_method=method,
                dataset_path=dataset_path,
                k=args.k,
                tenant_id=args.tenant_id,
                ai_runtime_url=args.ai_runtime_url,
                ai_runtime_token=args.ai_runtime_token,
                run_id=progress.run_id,
            )
            corpus_counts = CorpusCounts(published=len(docs), embedded=embedded_count)
            checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "dict")
            await run_embedding_generation_batch(
                records=records,
                config=batch_config,
                modules=modules,
                cards_by_module=cards_by_module,
                retriever=retriever,
                progress=progress,
                checkpoint_ctx=checkpoint_ctx,
            )
        finally:
            await retriever.aclose()

    artifacts = progress.dict_artifacts()
    e2e_summary = aggregate_e2e_summaries(artifacts)
    report = build_generation_batch_report(
        config=batch_config,
        artifacts=artifacts,
        corpus_published_count=corpus_counts.published,
        corpus_embedded_count=corpus_counts.embedded,
        e2e_summary=e2e_summary,
    )
    write_report_payload(report, args.output)
    delete_checkpoint(checkpoint_path(args.output))
    print(f"Wrote {args.output}")
    print(f"Evaluated {len(artifacts)} records with embedding retrieval + LLM generation")
    print(f"Run `rag-eval judge --input {args.output}` to score answers")
    return 0


async def _run_bm25_batch(args: argparse.Namespace) -> int:
    if args.generate:
        return await _run_bm25_generation_batch(args)

    dataset_path = args.dataset

    try:
        records = load_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Loaded {len(records)} records from {dataset_path}")

    with eval_tenant_scope(args.tenant_id):
        modules = await load_published_modules(tenant_id=args.tenant_id)
        cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
    docs = corpus_docs_from_modules(modules, cards_by_module_raw)
    records, _label_warnings = resolve_golden_labels(records, docs)

    cards_by_module = build_module_card_corpus(modules, cards_by_module_raw)
    resolution_issues = collect_golden_resolution_issues(records, docs, cards_by_module)
    skip_ids = unresolvable_golden_record_ids(resolution_issues)
    for issue in resolution_issues:
        print(f"warning: {issue.message}", file=sys.stderr)

    index = Bm25Index(docs)
    card_indexes = build_card_indexes(cards_by_module)
    use_pipeline = any(_record_has_card_eval(record) for record in records)

    ensure_resume_policy(args.output, args.resume)
    method = "bm25"
    config = _eval_run_config(args, method)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method}-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="retrieval",
    )
    corpus_counts = CorpusCounts(published=index.doc_count, embedded=None)
    checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "retrieval")

    for record in records:
        if progress.should_skip(record.id):
            continue
        if not record.is_answerable:
            after_record(
                progress,
                record.id,
                skip_kind=SkipKind.UNANSWERABLE,
                checkpoint_ctx=checkpoint_ctx,
            )
            continue
        if record.id in skip_ids:
            after_record(
                progress,
                record.id,
                skip_kind=SkipKind.UNRESOLVABLE,
                checkpoint_ctx=checkpoint_ctx,
            )
            continue
        module_hits = index.search(record.question, k=args.k)
        if use_pipeline and _record_has_card_eval(record):
            assert record.expected_module_id is not None
            assert record.expected_card_ids
            assert record.question_lang is not None
            pipeline_module_id = module_hits[0].module_id if module_hits else None
            card_hits = []
            if pipeline_module_id is not None:
                card_index = card_indexes.get(pipeline_module_id)
                if card_index is not None:
                    card_hits = card_index.search(record.question, k=args.k)
            artifact = artifact_from_pipeline_hits_with_lookup(
                record_id=record.id,
                category=record.category,
                question=record.question,
                is_answerable=record.is_answerable,
                relevant_module_ids=record.relevant_module_ids,
                expected_module_id=record.expected_module_id,
                expected_card_ids=record.expected_card_ids,
                question_lang=record.question_lang,
                module_hits=module_hits,
                card_hits=card_hits,
                cards_by_module=cards_by_module,
                k=args.k,
            )
        else:
            artifact = artifact_from_bm25_hits(
                record_id=record.id,
                category=record.category,
                question=record.question,
                expected_module=record.expected_module,
                is_answerable=record.is_answerable,
                relevant_module_ids=record.relevant_module_ids,
                hits=module_hits,
                k=args.k,
            )
        after_record(progress, record.id, artifact=artifact, checkpoint_ctx=checkpoint_ctx)

    report = build_batch_report(
        run_id=progress.run_id,
        retrieval_method=method,
        dataset_path=dataset_path,
        k=args.k,
        corpus_published_count=corpus_counts.published,
        corpus_embedded_count=None,
        artifacts=progress.retrieval_artifacts(),
        skipped_unanswerable_count=progress.skipped_unanswerable_count,
        skipped_unresolvable_count=progress.skipped_unresolvable_count,
    )
    write_batch_report(report, args.output)
    delete_checkpoint(checkpoint_path(args.output))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.md')}")
    print(f"Evaluated {report.evaluated_record_count} records; corpus={report.corpus_published_count}")
    print("Module metrics:")
    for key, value in report.aggregate_retrieval_metrics.items():
        print(f"  {key}: {value:.3f}")
    if report.aggregate_card_retrieval_metrics:
        print("Card metrics (pipeline):")
        for key, value in report.aggregate_card_retrieval_metrics.items():
            print(f"  {key}: {value:.3f}")
    return 0


async def _run_embedding_batch(args: argparse.Namespace) -> int:
    if args.generate:
        return await _run_embedding_generation_batch(args)

    dataset_path = args.dataset

    try:
        records = load_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ensure_resume_policy(args.output, args.resume)
    method = "embedding"
    config = _eval_run_config(args, method)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method}-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="retrieval",
    )

    with eval_tenant_scope(args.tenant_id):
        docs = await load_published_corpus(tenant_id=args.tenant_id)
        records, label_warnings = resolve_golden_labels(records, docs)
        for warning in label_warnings:
            print(f"warning: {warning}", file=sys.stderr)

        retriever = EmbeddingRetriever(
            tenant_id=args.tenant_id,
            base_url=args.ai_runtime_url,
            token=args.ai_runtime_token,
        )
        try:
            embedded_count = await retriever.embedded_count()
            if embedded_count == 0:
                print(
                    "warning: no published modules have embeddings; run the embedding worker first",
                    file=sys.stderr,
                )

            corpus_counts = CorpusCounts(published=len(docs), embedded=embedded_count)
            checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "retrieval")

            for record in records:
                if progress.should_skip(record.id):
                    continue
                if not record.is_answerable:
                    after_record(
                        progress,
                        record.id,
                        skip_kind=SkipKind.UNANSWERABLE,
                        checkpoint_ctx=checkpoint_ctx,
                    )
                    continue
                try:
                    hits = await retriever.search(record.question, k=args.k)
                except RuntimeError as exc:
                    print(f"error: {record.id}: {exc}", file=sys.stderr)
                    return 1
                artifact = artifact_from_embedding_hits(
                    record_id=record.id,
                    category=record.category,
                    question=record.question,
                    expected_module=record.expected_module,
                    is_answerable=record.is_answerable,
                    relevant_module_ids=record.relevant_module_ids,
                    hits=hits,
                    k=args.k,
                )
                after_record(progress, record.id, artifact=artifact, checkpoint_ctx=checkpoint_ctx)

            report = build_batch_report(
                run_id=progress.run_id,
                retrieval_method=method,
                dataset_path=dataset_path,
                k=args.k,
                corpus_published_count=corpus_counts.published,
                corpus_embedded_count=corpus_counts.embedded,
                artifacts=progress.retrieval_artifacts(),
                skipped_unanswerable_count=progress.skipped_unanswerable_count,
            )
            write_batch_report(report, args.output)
            delete_checkpoint(checkpoint_path(args.output))
            print(f"Wrote {args.output}")
            print(f"Wrote {args.output.with_suffix('.md')}")
            print(
                f"Evaluated {report.evaluated_record_count} records; "
                f"corpus published={report.corpus_published_count} embedded={embedded_count}"
            )
            for key, value in report.aggregate_retrieval_metrics.items():
                print(f"  {key}: {value:.3f}")
        finally:
            await retriever.aclose()
    return 0


async def _run_local_embedding_batch(args: argparse.Namespace) -> int:
    if args.generate:
        print("error: --generate is not supported for local_embedding", file=sys.stderr)
        return 2

    dataset_path = args.dataset

    try:
        records = load_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ensure_resume_policy(args.output, args.resume)
    method = "local_embedding"
    config = _eval_run_config(args, method)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method}-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="retrieval",
    )

    with eval_tenant_scope(args.tenant_id):
        docs = await load_published_corpus(tenant_id=args.tenant_id)
        records, label_warnings = resolve_golden_labels(records, docs)
        for warning in label_warnings:
            print(f"warning: {warning}", file=sys.stderr)

        retriever = EmbeddingRetriever(
            tenant_id=args.tenant_id,
            base_url=args.ai_runtime_url,
            token=args.ai_runtime_token,
            use_local=True,
        )
        try:
            embedded_count = await retriever.embedded_count()
            if embedded_count == 0:
                print(
                    "warning: no published modules have local embeddings; "
                    "run bin/backfill_module_local_embeddings.py first",
                    file=sys.stderr,
                )

            corpus_counts = CorpusCounts(published=len(docs), embedded=embedded_count)
            checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "retrieval")

            for record in records:
                if progress.should_skip(record.id):
                    continue
                if not record.is_answerable:
                    after_record(
                        progress,
                        record.id,
                        skip_kind=SkipKind.UNANSWERABLE,
                        checkpoint_ctx=checkpoint_ctx,
                    )
                    continue
                try:
                    hits = await retriever.search(record.question, k=args.k)
                except RuntimeError as exc:
                    print(f"error: {record.id}: {exc}", file=sys.stderr)
                    return 1
                artifact = artifact_from_embedding_hits(
                    record_id=record.id,
                    category=record.category,
                    question=record.question,
                    expected_module=record.expected_module,
                    is_answerable=record.is_answerable,
                    relevant_module_ids=record.relevant_module_ids,
                    hits=hits,
                    k=args.k,
                )
                after_record(progress, record.id, artifact=artifact, checkpoint_ctx=checkpoint_ctx)

            report = build_batch_report(
                run_id=progress.run_id,
                retrieval_method=method,
                dataset_path=dataset_path,
                k=args.k,
                corpus_published_count=corpus_counts.published,
                corpus_embedded_count=corpus_counts.embedded,
                artifacts=progress.retrieval_artifacts(),
                skipped_unanswerable_count=progress.skipped_unanswerable_count,
            )
            write_batch_report(report, args.output)
            delete_checkpoint(checkpoint_path(args.output))
            print(f"Wrote {args.output}")
            print(f"Wrote {args.output.with_suffix('.md')}")
            print(
                f"Evaluated {report.evaluated_record_count} records; "
                f"corpus published={report.corpus_published_count} embedded={embedded_count}"
            )
            for key, value in report.aggregate_retrieval_metrics.items():
                print(f"  {key}: {value:.3f}")
        finally:
            await retriever.aclose()
    return 0


async def _run_card_local_embedding_batch(args: argparse.Namespace) -> int:
    if args.generate:
        print("error: --generate is not supported for card_local_embedding", file=sys.stderr)
        return 2

    dataset_path = args.dataset

    try:
        records = load_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    ensure_resume_policy(args.output, args.resume)
    method = "card_local_embedding"
    config = _eval_run_config(args, method)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method}-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="retrieval",
    )

    with eval_tenant_scope(args.tenant_id):
        docs = await load_published_corpus(tenant_id=args.tenant_id)
        records, label_warnings = resolve_golden_labels(records, docs)
        for warning in label_warnings:
            print(f"warning: {warning}", file=sys.stderr)

        retriever = CardEmbeddingRetriever(
            tenant_id=args.tenant_id,
            base_url=args.ai_runtime_url,
            token=args.ai_runtime_token,
        )
        try:
            embedded_count = await retriever.embedded_count()
            if embedded_count == 0:
                print(
                    "warning: no published cards have local embeddings; "
                    "run bin/backfill_module_card_local_embeddings.py first",
                    file=sys.stderr,
                )

            corpus_counts = CorpusCounts(published=len(docs), embedded=embedded_count)
            checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "retrieval")

            for record in records:
                if progress.should_skip(record.id):
                    continue
                if not record.is_answerable:
                    after_record(
                        progress,
                        record.id,
                        skip_kind=SkipKind.UNANSWERABLE,
                        checkpoint_ctx=checkpoint_ctx,
                    )
                    continue
                try:
                    hits = await retriever.search(record.question, k=args.k)
                except RuntimeError as exc:
                    print(f"error: {record.id}: {exc}", file=sys.stderr)
                    return 1
                artifact = artifact_from_card_embedding_hits(
                    record_id=record.id,
                    category=record.category,
                    question=record.question,
                    expected_module=record.expected_module,
                    is_answerable=record.is_answerable,
                    relevant_module_ids=record.relevant_module_ids,
                    expected_card_ids=record.expected_card_ids,
                    hits=hits,
                    k=args.k,
                )
                after_record(progress, record.id, artifact=artifact, checkpoint_ctx=checkpoint_ctx)

            report = build_batch_report(
                run_id=progress.run_id,
                retrieval_method=method,
                dataset_path=dataset_path,
                k=args.k,
                corpus_published_count=corpus_counts.published,
                corpus_embedded_count=corpus_counts.embedded,
                artifacts=progress.retrieval_artifacts(),
                skipped_unanswerable_count=progress.skipped_unanswerable_count,
            )
            write_batch_report(report, args.output)
            delete_checkpoint(checkpoint_path(args.output))
            print(f"Wrote {args.output}")
            print(f"Wrote {args.output.with_suffix('.md')}")
            print(
                f"Evaluated {report.evaluated_record_count} records; "
                f"corpus published={report.corpus_published_count} embedded_cards={embedded_count}"
            )
            print("Module metrics (derived from card hits):")
            for key, value in report.aggregate_retrieval_metrics.items():
                print(f"  {key}: {value:.3f}")
            if report.aggregate_card_retrieval_metrics:
                print("Card metrics:")
                for key, value in report.aggregate_card_retrieval_metrics.items():
                    print(f"  {key}: {value:.3f}")
        finally:
            await retriever.aclose()
    return 0


async def _run_rag_e2e_batch(args: argparse.Namespace, *, local_card: bool) -> int:
    method_name = "local_rag" if local_card else "rag"
    if args.query is not None:
        print(
            f"error: {method_name} method does not support a positional query; use batch mode",
            file=sys.stderr,
        )
        return 2

    dataset_path = args.dataset
    try:
        records = load_rag_golden_dataset(dataset_path, language=args.language)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.record_id is not None:
        records = [record for record in records if record.id == args.record_id]
        if not records:
            print(f"error: record id {args.record_id!r} not found in dataset", file=sys.stderr)
            return 1
    elif args.limit is not None:
        if args.limit <= 0:
            print("error: --limit must be positive", file=sys.stderr)
            return 2
        records = records[: args.limit]

    ensure_resume_policy(args.output, args.resume)
    config = _eval_run_config(args, method_name, local_card=local_card)
    run_id = args.run_id or datetime.now(UTC).strftime(f"{method_name}-%Y%m%d-%H%M%S")
    progress = init_progress(
        output_path=args.output,
        resume=args.resume,
        config=config,
        run_id=run_id,
        artifact_kind="dict",
    )
    corpus_counts: CorpusCounts | None = None
    embedded_count = 0

    with eval_tenant_scope(args.tenant_id):
        docs = await load_published_corpus(tenant_id=args.tenant_id)
        published_module_ids = {doc.module_id for doc in docs}
        module_warnings = validate_expected_module_ids(records, published_module_ids)
        for warning in module_warnings:
            print(f"warning: {warning}", file=sys.stderr)

        modules = await load_published_modules(tenant_id=args.tenant_id)
        cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
        cards_by_module = build_module_card_corpus(modules, cards_by_module_raw)
        card_warnings = validate_expected_card_ids(records, cards_by_module)
        for warning in card_warnings:
            print(f"warning: {warning}", file=sys.stderr)

        if local_card:
            embedded_count = await count_local_embedded_published_cards(tenant_id=args.tenant_id)
            if embedded_count == 0:
                print(
                    "warning: no published cards have local embeddings; "
                    "run bin/backfill_module_card_local_embeddings.py first",
                    file=sys.stderr,
                )
        else:
            embedded_count = await count_embedded_published_modules(tenant_id=args.tenant_id)
            if embedded_count == 0:
                print(
                    "warning: no published modules have embeddings; run the embedding worker first",
                    file=sys.stderr,
                )

        llm_judge: LlmJudge | None = None
        if args.llm_judge:
            llm_judge = LlmJudge(
                AIRuntimeClient(base_url=args.ai_runtime_url, token=args.ai_runtime_token),
            )

        runner = RagQueryRunner(
            tenant_id=args.tenant_id,
            base_url=args.ai_runtime_url,
            token=args.ai_runtime_token,
            cards_by_module=cards_by_module,
            llm_judge=llm_judge,
            local_card=local_card,
        )
        corpus_counts = CorpusCounts(published=len(docs), embedded=embedded_count)
        checkpoint_ctx = _checkpoint_context(args, config, corpus_counts, "dict")
        try:
            for index, record in enumerate(records, start=1):
                if progress.should_skip(record.id):
                    continue
                preview = record.query if len(record.query) <= 80 else f"{record.query[:80]}..."
                print(f"[{index}/{len(records)}] {record.id}: {preview}", file=sys.stderr)
                result = await runner.run_record(record, k=args.k)
                if result.error:
                    print(f"warning: {record.id}: {result.error}", file=sys.stderr)
                artifact_dict = rag_result_to_artifact_dict(result)
                after_record(
                    progress,
                    record.id,
                    artifact=artifact_dict,
                    checkpoint_ctx=checkpoint_ctx,
                )
        finally:
            await runner.aclose()

    if corpus_counts is None:
        raise RuntimeError("rag batch did not initialize corpus counts")
    artifact_dicts = progress.dict_artifacts()
    e2e_summary = aggregate_e2e_summaries(artifact_dicts)
    report = build_rag_batch_report(
        run_id=progress.run_id,
        dataset_path=dataset_path,
        k=args.k,
        corpus_published_count=corpus_counts.published,
        corpus_embedded_count=corpus_counts.embedded,
        artifact_dicts=artifact_dicts,
        e2e_summary=e2e_summary,
    )
    title_key = "local_rag" if local_card else "rag"
    write_rag_batch_report(report, args.output, title_key=title_key)
    delete_checkpoint(checkpoint_path(args.output))
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.md')}")
    embedded_label = "embedded_cards" if local_card else "embedded"
    print(
        f"Evaluated {report.evaluated_record_count} records; "
        f"corpus published={report.corpus_published_count} {embedded_label}={embedded_count}"
    )
    if not args.llm_judge:
        print(f"Run `rag-eval judge --input {args.output}` to score answers with LLM judge")
    print("E2E metrics:")
    print(f"  avg_token_f1: {float(e2e_summary['avg_token_f1']):.3f}")
    print(f"  avg_token_recall: {float(e2e_summary.get('avg_token_recall', 0.0)):.3f}")
    print(f"  abstention_rate: {float(e2e_summary['abstention_rate']):.3f}")
    print(f"  false_refusal_rate: {float(e2e_summary['false_refusal_rate']):.3f}")
    context_summary = e2e_summary.get("context_summary")
    if isinstance(context_summary, dict) and context_summary:
        print("Context metrics:")
        for key, value in context_summary.items():
            print(f"  {key}: {float(value):.3f}")
    citation_summary = e2e_summary.get("citation_summary")
    if isinstance(citation_summary, dict) and citation_summary:
        print("Citation metrics:")
        for key, value in citation_summary.items():
            print(f"  {key}: {float(value):.3f}")
    judge_summary = e2e_summary.get("judge_summary")
    if isinstance(judge_summary, dict) and judge_summary:
        _print_judge_summary(judge_summary)
    if report.retrieval_summary:
        print("Retrieval metrics:")
        for key, value in report.retrieval_summary.items():
            print(f"  {key}: {value:.3f}")
    return 0


async def _run_rag_batch(args: argparse.Namespace) -> int:
    return await _run_rag_e2e_batch(args, local_card=False)


async def _run_local_rag_batch(args: argparse.Namespace) -> int:
    return await _run_rag_e2e_batch(args, local_card=True)


async def _run_validate(args: argparse.Namespace) -> int:
    dataset_path = args.dataset
    try:
        issues = validate_golden_dataset(dataset_path)
        records = [item for item in load_golden_source_array(dataset_path) if isinstance(item, dict)]
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    with eval_tenant_scope(args.tenant_id):
        modules = await load_published_modules(tenant_id=args.tenant_id)
        cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
    published_module_ids = {str(module.id) for module in modules}
    published_card_ids: set[str] = set()
    card_to_module: dict[str, str] = {}
    for module_id, cards in cards_by_module_raw.items():
        for card in cards:
            card_id = str(card["id"])
            published_card_ids.add(card_id)
            card_to_module[card_id] = str(module_id)

    issues.extend(
        validate_golden_corpus_alignment(
            records,
            published_module_ids=published_module_ids,
            published_card_ids=published_card_ids,
        )
    )
    issues.extend(
        validate_golden_card_module_alignment(
            records,
            card_to_module=card_to_module,
        )
    )

    if issues:
        for issue in issues:
            print(f"{issue.record_id}: {issue.message}", file=sys.stderr)
        print(f"validation failed: {len(issues)} issue(s)", file=sys.stderr)
        return 1

    print(f"validation passed: {len(records)} records")
    return 0


async def _run_coverage(args: argparse.Namespace) -> int:
    try:
        with eval_tenant_scope(args.tenant_id):
            report = await build_coverage_report(
                args.dataset,
                tenant_id=args.tenant_id,
                min_records_per_module=args.min_records_per_module,
            )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    write_coverage_report(report, args.output)
    print(f"Wrote {args.output}")
    print(f"Wrote {args.output.with_suffix('.md')}")
    print(
        f"Coverage: modules={report.covered_module_count}/{report.published_module_count}, "
        f"cards={report.card_reference_rate:.1%}, records={report.record_count}"
    )
    return 0


def _run_golden_compile(args: argparse.Namespace) -> int:
    try:
        output = compile_manifest(args.manifest, output=args.output)
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote {output}")
    return 0


def _print_judge_summary(judge_summary: dict[str, object]) -> None:
    if not judge_summary:
        return
    print("LLM judge:")
    for key, value in judge_summary.items():
        if key == "by_answerable" and isinstance(value, dict):
            print("  by_answerable:")
            for bucket, metrics in value.items():
                if not isinstance(metrics, dict):
                    continue
                formatted = ", ".join(f"{k}={float(v):.3f}" for k, v in metrics.items())
                print(f"    {bucket}: {formatted}")
            continue
        if isinstance(value, (int, float)):
            print(f"  {key}: {float(value):.3f}")


async def _run_judge(args: argparse.Namespace) -> int:
    output_path = args.output or args.input.with_name(f"{args.input.stem}-judged.json")
    client = AIRuntimeClient(base_url=args.ai_runtime_url, token=args.ai_runtime_token)
    cards_by_module: dict | None = None
    try:
        with eval_tenant_scope(args.tenant_id):
            modules = await load_published_modules(tenant_id=args.tenant_id)
            cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
            cards_by_module = build_module_card_corpus(modules, cards_by_module_raw)
            report = await judge_report_file(
                args.input,
                client=client,
                cards_by_module=cards_by_module,
            )
    except (FileNotFoundError, ValueError, OSError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        await client.aclose()

    write_report_payload(report, output_path)
    print(f"Wrote {output_path}")
    judge_summary = report.get("judge_summary")
    if isinstance(judge_summary, dict):
        _print_judge_summary(judge_summary)
    e2e = report.get("e2e_summary")
    if isinstance(e2e, dict):
        nested = e2e.get("judge_summary")
        if isinstance(nested, dict) and nested != judge_summary:
            _print_judge_summary(nested)
    return 0


async def _run_tool(args: argparse.Namespace) -> int:
    if args.command == "validate":
        return await _run_validate(args)
    if args.command == "coverage":
        return await _run_coverage(args)
    if args.command == "golden-compile":
        return _run_golden_compile(args)
    if args.command == "judge":
        return await _run_judge(args)
    print(f"error: unknown command {args.command!r}", file=sys.stderr)
    return 2


async def _async_main(args: argparse.Namespace) -> int:
    if getattr(args, "mode", "eval") == "tool":
        return await _run_tool(args)
    if args.method == "rag":
        return await _run_rag_batch(args)
    if args.method == "local_rag":
        return await _run_local_rag_batch(args)
    if args.method == "bm25":
        if args.query is None:
            return await _run_bm25_batch(args)
        return await _run_bm25_single_query(args)
    if args.method == "local_embedding":
        if args.query is None:
            return await _run_local_embedding_batch(args)
        return await _run_local_embedding_single_query(args)
    if args.method == "card_local_embedding":
        if args.query is None:
            return await _run_card_local_embedding_batch(args)
        return await _run_card_local_embedding_single_query(args)
    if args.method == "embedding":
        if args.query is None:
            return await _run_embedding_batch(args)
        return await _run_embedding_single_query(args)
    print(f"error: unknown method {args.method!r}", file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_cli_args(argv)
    if getattr(args, "mode", "eval") == "eval":
        _apply_method_defaults(args)
        if args.k <= 0:
            print("error: --k must be positive", file=sys.stderr)
            return 2
        if args.checkpoint_interval < 0:
            print("error: --checkpoint-interval must be non-negative", file=sys.stderr)
            return 2
    return asyncio.run(_async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
