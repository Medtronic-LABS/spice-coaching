FROM python:3.12-slim AS build

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

COPY pyproject.toml uv.lock /app/
COPY packages/contracts/pyproject.toml /app/packages/contracts/
COPY packages/foundation/pyproject.toml /app/packages/foundation/
COPY services/platform/pyproject.toml /app/services/platform/
COPY services/ai-runtime/pyproject.toml /app/services/ai-runtime/
COPY eval/pyproject.toml /app/eval/

RUN uv sync --locked --only-group docs --no-install-project --no-install-workspace
ENV PATH="/app/.venv/bin:$PATH"

COPY mkdocs.yml .
COPY docs docs

RUN mkdocs build -d /site

FROM nginx:1.27-alpine AS static

COPY --from=build /site /usr/share/nginx/html
