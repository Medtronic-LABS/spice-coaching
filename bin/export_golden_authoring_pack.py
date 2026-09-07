#!/usr/bin/env python3
"""Export published module/card inventory for golden dataset authoring.

Writes:
  eval/rag/golden/authoring/corpus_inventory.json
  eval/rag/golden/authoring/<domain>.md  (one stub per domain)

Usage:
    uv run python bin/export_golden_authoring_pack.py [--tenant-id N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from eval.rag.corpus import load_cards_by_module_ids, load_published_modules
from mc_foundation.locale import LOCALIZED_CARD_TEXT_FIELDS, localized_primary_text
from platform_service.localized import primary_text


def _localized_text(value: object, *, locale: str = "bn") -> str:
    if isinstance(value, dict):
        text = value.get(locale) or localized_primary_text(value, locale)
        return str(text).strip() if text is not None else ""
    if isinstance(value, list):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()


def _card_excerpt(card: dict[str, object], *, max_len: int = 240) -> str:
    parts: list[str] = []
    for field in LOCALIZED_CARD_TEXT_FIELDS:
        text = _localized_text(card.get(field))
        if text:
            parts.append(text)
    combined = " ".join(parts)
    if len(combined) <= max_len:
        return combined
    return combined[: max_len - 3].rstrip() + "..."


async def _build_inventory(*, tenant_id: int | None) -> dict[str, object]:
    modules = await load_published_modules(tenant_id=tenant_id)
    cards_by_module = await load_cards_by_module_ids([module.id for module in modules])

    domain_modules: dict[str, list[dict[str, object]]] = {}
    inventory_modules: list[dict[str, object]] = []

    for module in modules:
        domain = str(getattr(module, "domain", "") or "unknown")
        title_localized = module.title_localized or {}
        cards_raw = cards_by_module.get(module.id, [])
        cards = sorted(cards_raw, key=lambda row: int(row.get("card_order") or 0))
        card_entries = [
            {
                "id": str(card["id"]),
                "card_order": int(card.get("card_order") or 0),
                "title_bn": _localized_text(card.get("title_localized"), locale="bn")
                or _localized_text(card.get("title")),
                "title_en": _localized_text(card.get("title_localized"), locale="en"),
                "excerpt_bn": _card_excerpt(card),
            }
            for card in cards
        ]
        module_entry = {
            "id": str(module.id),
            "domain": domain,
            "title_bn": (title_localized.get("bn") or "").strip() or primary_text(title_localized),
            "title_en": (title_localized.get("en") or "").strip(),
            "card_count": len(card_entries),
            "cards": card_entries,
        }
        inventory_modules.append(module_entry)
        domain_modules.setdefault(domain, []).append(module_entry)

    return {
        "module_count": len(inventory_modules),
        "total_cards": sum(module["card_count"] for module in inventory_modules),
        "modules": inventory_modules,
        "by_domain": domain_modules,
    }


def _write_domain_stubs(output_dir: Path, by_domain: dict[str, list[dict[str, object]]]) -> None:
    for domain, modules in sorted(by_domain.items()):
        lines = [
            f"# Golden authoring stub — {domain}",
            "",
            "Use card IDs below when authoring `source_card_id` labels.",
            "",
        ]
        for module in modules:
            lines.extend(
                [
                    f"## {module['title_bn']}",
                    "",
                    f"- module_id: `{module['id']}`",
                    f"- cards: {module['card_count']}",
                    "",
                ]
            )
            for card in module["cards"]:
                lines.append(f"- `{card['id']}` — {card['title_bn'] or card['title_en']}")
                if card["excerpt_bn"]:
                    lines.append(f"  - excerpt: {card['excerpt_bn']}")
            lines.append("")
        (output_dir / f"{domain}.md").write_text("\n".join(lines), encoding="utf-8")


async def _run(*, tenant_id: int | None, output_dir: Path) -> int:
    inventory = await _build_inventory(tenant_id=tenant_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    inventory_path = output_dir / "corpus_inventory.json"
    inventory_path.write_text(
        json.dumps(
            {
                "module_count": inventory["module_count"],
                "total_cards": inventory["total_cards"],
                "modules": inventory["modules"],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _write_domain_stubs(output_dir, inventory["by_domain"])

    print(f"Wrote {inventory_path}")
    print(f"Modules: {inventory['module_count']}, cards: {inventory['total_cards']}")
    print(f"Domain stubs: {output_dir}/*.md")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Export golden dataset authoring pack.")
    parser.add_argument("--tenant-id", type=int, default=None)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("eval/rag/golden/authoring"),
    )
    args = parser.parse_args()
    return asyncio.run(_run(tenant_id=args.tenant_id, output_dir=args.output_dir))


if __name__ == "__main__":
    raise SystemExit(main())
