# Golden dataset for RAG evaluation

Product procedure lives in [docs/architecture/rag-evaluation.md](../../../docs/architecture/rag-evaluation.md).

This directory holds golden records, the compile manifest, taxonomy, and generated authoring files.

| File | Role |
|------|------|
| [Golden_Dataset.manifest.json](Golden_Dataset.manifest.json) | Primary modular authoring manifest |
| [Golden_Dataset.json](Golden_Dataset.json) | Compiled bilingual superset |
| [pilot_records.json](pilot_records.json) | Hand-curated Q001–Q025 pilot |
| [golden_dataset.json](golden_dataset.json) | Bangla-only reference rows. UUIDs may not match the current database. |
| [authoring/](authoring/) | Generated corpus inventory for SMEs. Working files, not product docs. |

Compile:

```bash
uv run python -m eval.rag golden-compile --manifest eval/rag/golden/Golden_Dataset.manifest.json
```

Validate:

```bash
uv run python -m eval.rag validate --dataset eval/rag/golden/Golden_Dataset.manifest.json
```

Run methods are listed in [docs/architecture/rag-evaluation.md](../../../docs/architecture/rag-evaluation.md).
