"""Coverage analysis for bilingual golden datasets."""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from eval.rag.corpus import build_module_card_corpus, load_cards_by_module_ids, load_published_modules
from eval.rag.golden_manifest import load_golden_source_array


@dataclass
class CoverageReport:
    dataset_path: str
    generated_at: str
    record_count: int
    answerable_yes: int
    answerable_no: int
    answerable_partial: int
    published_module_count: int
    published_card_count: int
    covered_module_count: int
    uncovered_module_ids: list[str] = field(default_factory=list)
    uncovered_modules: list[dict[str, str]] = field(default_factory=list)
    stale_module_ids: list[str] = field(default_factory=list)
    stale_card_ids: list[str] = field(default_factory=list)
    unreferenced_card_count: int = 0
    unreferenced_card_ids: list[str] = field(default_factory=list)
    card_reference_rate: float = 0.0
    query_type_counts: dict[str, int] = field(default_factory=dict)
    linguistic_variation_counts: dict[str, int] = field(default_factory=dict)
    module_record_counts: dict[str, int] = field(default_factory=dict)
    modules_below_minimum: list[dict[str, object]] = field(default_factory=list)


def _module_title(module) -> str:
    localized = module.title_localized or {}
    return (localized.get("bn") or "").strip() or (localized.get("en") or "").strip() or str(module.id)


async def build_coverage_report(
    dataset_path: Path,
    *,
    tenant_id: int | None = None,
    min_records_per_module: int = 4,
) -> CoverageReport:
    raw_records = load_golden_source_array(dataset_path)
    records = [item for item in raw_records if isinstance(item, dict)]

    modules = await load_published_modules(tenant_id=tenant_id)
    cards_by_module_raw = await load_cards_by_module_ids([module.id for module in modules])
    cards_by_module = build_module_card_corpus(modules, cards_by_module_raw)

    published_module_ids = {str(module.id): module for module in modules}
    published_card_ids: set[str] = set()
    card_to_module: dict[str, str] = {}
    for module_id, cards in cards_by_module.items():
        for card in cards:
            card_id = str(card.card_id)
            published_card_ids.add(card_id)
            card_to_module[card_id] = str(module_id)

    referenced_modules: set[str] = set()
    referenced_cards: set[str] = set()
    stale_module_ids: set[str] = set()
    stale_card_ids: set[str] = set()
    module_record_counts: Counter[str] = Counter()
    query_type_counts: Counter[str] = Counter()
    linguistic_counts: Counter[str] = Counter()
    answerable_yes = answerable_no = answerable_partial = 0

    for item in records:
        answerable = str(item.get("answerable", "yes")).strip().casefold()
        if answerable == "no":
            answerable_no += 1
        elif answerable == "partial":
            answerable_partial += 1
        else:
            answerable_yes += 1

        query_type = str(item.get("query_type", "unknown"))
        query_type_counts[query_type] += 1
        linguistic = str(item.get("linguistic_variation", "unknown"))
        linguistic_counts[linguistic] += 1

        module_ids = [str(value) for value in (item.get("module_id") or [])]
        card_ids = [str(value) for value in (item.get("source_card_id") or [])]

        for module_id in module_ids:
            if module_id in published_module_ids:
                referenced_modules.add(module_id)
                if answerable != "no":
                    module_record_counts[module_id] += 1
            else:
                stale_module_ids.add(module_id)

        for card_id in card_ids:
            if card_id in published_card_ids:
                referenced_cards.add(card_id)
            else:
                stale_card_ids.add(card_id)

    uncovered_module_ids = sorted(set(published_module_ids) - referenced_modules)
    uncovered_modules = [
        {
            "module_id": module_id,
            "title_bn": _module_title(published_module_ids[module_id]),
            "domain": str(getattr(published_module_ids[module_id], "domain", "") or ""),
            "card_count": len(cards_by_module.get(UUID(module_id), [])),
        }
        for module_id in uncovered_module_ids
    ]

    unreferenced_card_ids = sorted(published_card_ids - referenced_cards)
    card_reference_rate = len(referenced_cards) / len(published_card_ids) if published_card_ids else 0.0

    modules_below_minimum = []
    for module_id, module in published_module_ids.items():
        count = module_record_counts.get(module_id, 0)
        if count < min_records_per_module:
            modules_below_minimum.append(
                {
                    "module_id": module_id,
                    "title_bn": _module_title(module),
                    "record_count": count,
                    "minimum": min_records_per_module,
                }
            )

    return CoverageReport(
        dataset_path=str(dataset_path),
        generated_at=datetime.now(UTC).isoformat(),
        record_count=len(records),
        answerable_yes=answerable_yes,
        answerable_no=answerable_no,
        answerable_partial=answerable_partial,
        published_module_count=len(published_module_ids),
        published_card_count=len(published_card_ids),
        covered_module_count=len(referenced_modules),
        uncovered_module_ids=uncovered_module_ids,
        uncovered_modules=uncovered_modules,
        stale_module_ids=sorted(stale_module_ids),
        stale_card_ids=sorted(stale_card_ids),
        unreferenced_card_count=len(unreferenced_card_ids),
        unreferenced_card_ids=unreferenced_card_ids[:50],
        card_reference_rate=card_reference_rate,
        query_type_counts=dict(query_type_counts),
        linguistic_variation_counts=dict(linguistic_counts),
        module_record_counts=dict(module_record_counts),
        modules_below_minimum=sorted(
            modules_below_minimum,
            key=lambda row: (row["record_count"], str(row["title_bn"])),
        ),
    )


def write_coverage_report(report: CoverageReport, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(asdict(report), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    md_lines = [
        "# Golden Dataset Coverage Report",
        "",
        f"Dataset: `{report.dataset_path}`",
        f"Generated: {report.generated_at}",
        "",
        "## Summary",
        "",
        f"- Records: **{report.record_count}** (yes={report.answerable_yes}, no={report.answerable_no}, partial={report.answerable_partial})",
        f"- Published modules: **{report.published_module_count}**",
        f"- Covered modules: **{report.covered_module_count}**",
        f"- Published cards: **{report.published_card_count}**",
        f"- Referenced cards: **{report.published_card_count - report.unreferenced_card_count}** ({report.card_reference_rate:.1%})",
        f"- Stale module IDs: **{len(report.stale_module_ids)}**",
        f"- Stale card IDs: **{len(report.stale_card_ids)}**",
        "",
        "## Query types",
        "",
    ]
    for key, value in sorted(report.query_type_counts.items()):
        md_lines.append(f"- {key}: {value}")
    md_lines.extend(["", "## Modules below minimum", ""])
    if not report.modules_below_minimum:
        md_lines.append("All modules meet the minimum record threshold.")
    else:
        for row in report.modules_below_minimum:
            md_lines.append(
                f"- `{row['module_id']}` ({row['title_bn']}): {row['record_count']}/{row['minimum']}"
            )
    md_lines.extend(["", "## Uncovered modules", ""])
    if not report.uncovered_modules:
        md_lines.append("All published modules are referenced.")
    else:
        for row in report.uncovered_modules:
            md_lines.append(
                f"- `{row['module_id']}` — {row['title_bn']} ({row['domain']}, {row['card_count']} cards)"
            )
    output.with_suffix(".md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
