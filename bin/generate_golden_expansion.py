#!/usr/bin/env python3
"""Generate bilingual golden dataset expansion records from published corpus.

Reads live module/card content via ai-runtime (pilot records as n-shot examples)
and writes domain shard files under eval/rag/golden/records/.
Does not overwrite hand-curated pilot records (Q001–Q025).

Usage:
    uv run python bin/generate_golden_expansion.py [--tenant-id N]
    uv run python bin/generate_golden_expansion.py --template-fallback
    uv run python bin/generate_golden_expansion.py --domain anc
    uv run python bin/generate_golden_expansion.py --export-prompts
    uv run python bin/generate_golden_expansion.py --domain anc --export-prompts
    uv run python bin/generate_golden_expansion.py --from-response
    uv run python bin/generate_golden_expansion.py --domain anc \
        --from-response eval/rag/golden/authoring/prompts/anc_batch0.response.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from eval.rag.golden_expansion import (
    GOLDEN_DIR,
    PROMPTS_DIR,
    export_expansion_prompts,
    generate_expansion_shards,
    ingest_expansion_responses,
    shard_for_domain,
    write_expansion_shards_from_domains,
)
from platform_service.integrations.ai_runtime_client import AIRuntimeClient

RECORDS_DIR = GOLDEN_DIR / "records"


def _write_shards(shards: dict[str, list[dict[str, object]]]) -> None:
    RECORDS_DIR.mkdir(parents=True, exist_ok=True)
    for shard_name, records in shards.items():
        path = RECORDS_DIR / shard_name
        path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote {path} ({len(records)} records)")


def _write_manifest() -> None:
    manifest = {
        "name": "Golden_Dataset",
        "description": "Bilingual golden dataset for RAG evaluation (compiled superset).",
        "compiled_output": "Golden_Dataset.json",
        "records": [
            "records/anc.json",
            "records/pnc.json",
            "records/neonatal.json",
            "records/infectious.json",
            "records/diarrhea_nutrition.json",
            "records/immunisation_documentation.json",
            "records/out_of_scope.json",
        ],
    }
    manifest_path = GOLDEN_DIR / "Golden_Dataset.manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {manifest_path}")


async def _run_export_prompts(
    *,
    tenant_id: int | None,
    domain: str | None,
    prompts_dir: Path,
) -> int:
    try:
        written = await export_expansion_prompts(
            tenant_id=tenant_id,
            output_dir=prompts_dir,
            domain_filter=domain,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not written:
        scope = domain if domain else "all domains"
        print(f"No prompts exported for {scope} (nothing to generate).")
        return 0
    for path in written:
        print(f"Wrote {path}")
    return 0


async def _run_from_response(
    *,
    tenant_id: int | None,
    domain: str | None,
    response_path: Path,
) -> int:
    try:
        by_domain = await ingest_expansion_responses(
            response_path=response_path,
            tenant_id=tenant_id,
            domain_filter=domain,
        )
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if not by_domain:
        scope = domain if domain else "all domains"
        print(f"No valid records ingested for {scope} from {response_path}", file=sys.stderr)
        return 1

    written = write_expansion_shards_from_domains(records_by_domain=by_domain)
    for shard_name in sorted(written):
        expansion_count = sum(
            len(records) for domain, records in by_domain.items() if shard_for_domain(domain) == shard_name
        )
        print(f"Wrote {written[shard_name]} ({expansion_count} expansion records)")
    return 0


async def _run_generate(
    *,
    tenant_id: int | None,
    ai_runtime_url: str | None,
    ai_runtime_token: str | None,
    template_fallback: bool,
    domain: str | None,
) -> int:
    client: AIRuntimeClient | None = None
    if not template_fallback:
        client = AIRuntimeClient(base_url=ai_runtime_url, token=ai_runtime_token)

    try:
        shards = await generate_expansion_shards(
            tenant_id=tenant_id,
            client=client,
            template_fallback=template_fallback,
            domain_filter=domain,
        )
    finally:
        if client is not None:
            await client.aclose()

    _write_shards(shards)
    if domain is None:
        _write_manifest()
    total = sum(len(records) for records in shards.values())
    print(f"Total records across shards: {total}")
    return 0


async def _run(
    *,
    tenant_id: int | None,
    ai_runtime_url: str | None,
    ai_runtime_token: str | None,
    template_fallback: bool,
    domain: str | None,
    export_prompts: bool,
    from_response: Path | None,
    prompts_dir: Path,
) -> int:
    if export_prompts:
        if from_response is not None:
            print("error: --export-prompts and --from-response are mutually exclusive", file=sys.stderr)
            return 2
        if template_fallback:
            print("error: --export-prompts cannot be used with --template-fallback", file=sys.stderr)
            return 2
        return await _run_export_prompts(
            tenant_id=tenant_id,
            domain=domain,
            prompts_dir=prompts_dir,
        )

    if from_response is not None:
        if template_fallback:
            print("error: --from-response cannot be used with --template-fallback", file=sys.stderr)
            return 2
        return await _run_from_response(
            tenant_id=tenant_id,
            domain=domain,
            response_path=from_response,
        )

    return await _run_generate(
        tenant_id=tenant_id,
        ai_runtime_url=ai_runtime_url,
        ai_runtime_token=ai_runtime_token,
        template_fallback=template_fallback,
        domain=domain,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate golden dataset expansion shards.")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument(
        "--ai-runtime-url",
        default=None,
        help="ai-runtime base URL override (default: platform AI_RUNTIME_BASE_URL)",
    )
    parser.add_argument(
        "--ai-runtime-token",
        default=None,
        help="ai-runtime internal token override (default: platform AI_RUNTIME_TOKEN)",
    )
    parser.add_argument(
        "--template-fallback",
        action="store_true",
        help="Use deterministic templates instead of ai-runtime LLM generation",
    )
    parser.add_argument(
        "--domain",
        default=None,
        help="Limit to a single domain (e.g. anc, pnc, malaria); optional for manual export/ingest",
    )
    parser.add_argument(
        "--export-prompts",
        action="store_true",
        help="Export per-batch LLM prompts for manual authoring (all domains unless --domain is set)",
    )
    parser.add_argument(
        "--from-response",
        nargs="?",
        const=PROMPTS_DIR,
        default=None,
        type=Path,
        metavar="PATH",
        help=(
            "Ingest manual LLM JSON response file or directory "
            f"(default: {PROMPTS_DIR}; all domains unless --domain is set)"
        ),
    )
    parser.add_argument(
        "--prompts-dir",
        type=Path,
        default=PROMPTS_DIR,
        help="Output directory for --export-prompts",
    )
    args = parser.parse_args()
    return asyncio.run(
        _run(
            tenant_id=args.tenant_id,
            ai_runtime_url=args.ai_runtime_url,
            ai_runtime_token=args.ai_runtime_token,
            template_fallback=args.template_fallback,
            domain=args.domain,
            export_prompts=args.export_prompts,
            from_response=args.from_response,
            prompts_dir=args.prompts_dir,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
