# syntax=docker/dockerfile:1
# Build context is the REPO ROOT (workspace deps live in sibling dirs):
#   docker build -f apps/http/Dockerfile -t alexandria-http .
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

# 1) Copy only manifests first so dependency install is cached across source changes.
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/engine/pyproject.toml apps/engine/pyproject.toml
COPY apps/http/pyproject.toml apps/http/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package alexandria-http --no-install-workspace --no-dev

# 2) Copy the workspace members this app needs, then install them (editable).
#    The API embeds the engine in-process but NOT its heavy [ml] extra (no torch here).
COPY packages/core packages/core
COPY apps/engine apps/engine
COPY apps/http apps/http
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package alexandria-http --no-dev

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=builder /app /app
ENV PATH="/app/.venv/bin:$PATH" ALEX_DB_PATH=/data/alexandria.db
EXPOSE 8000
CMD ["python", "-m", "api"]
