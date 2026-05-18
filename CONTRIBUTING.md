# Contributing

Thanks for your interest in contributing. This repository hosts the
MicroCoaching backend (platform service + ai-runtime service).

## Development setup

```bash
git clone https://github.com/Medtronic-LABS/spice-coaching.git
cd spice-coaching
cp .env.example .env   # fill in GOOGLE_USE_VERTEX or GOOGLE_API_KEY
uv sync --locked --all-packages --group dev
```

Python 3.12, uv-managed workspace, single `uv.lock` at the repo root.

## Run tests

```bash
uv run pytest                          # full suite (some tests need Postgres)
uv run pytest -m "not requires_db"     # subset that runs without infra
```

## Lint and format

```bash
uv run ruff check .
uv run ruff format --check .
```

Both must pass before opening a PR. CI runs the same commands.

## Branches and pull requests

- Branch from `main`; name branches `<area>/<short-description>`
  (e.g. `platform/quiz-retrigger`, `ai-runtime/openai-fallback`).
- Keep PRs scoped — one logical change per PR.
- Fill in the PR template. Link the issue if there is one.
- Squash-merge is the default.

## Commit hygiene

- Conventional-commit-style summaries are encouraged
  (`feat:`, `fix:`, `chore:`, `docs:`).
- Don't commit secrets, real PHI, or partner-confidential training data.
- The `seed/` directory has its own README explaining redistribution
  rules — read it before adding new seed files.

## Code of conduct

By participating you agree to abide by the project's code of conduct.
Report concerns to the address in `SECURITY.md`.

## Security

Do **not** open public issues for suspected vulnerabilities. See
`SECURITY.md` for the private disclosure address.
