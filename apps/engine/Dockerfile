# syntax=docker/dockerfile:1
# Build context is the REPO ROOT:
#   docker build -f apps/engine/Dockerfile -t alexandria-engine .
# This image includes the [ml] extra (sentence-transformers + torch) — it is large.
# For real GPU inference, swap the runtime base for an NVIDIA CUDA / PyTorch image and
# run with `--gpus all` (see docker-compose.yml for the GPU reservation stanza).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/pyproject.toml
COPY apps/engine/pyproject.toml apps/engine/pyproject.toml
COPY apps/http/pyproject.toml apps/http/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package alexandria-engine --extra ml --no-install-workspace --no-dev

COPY packages/core packages/core
COPY apps/engine apps/engine
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --package alexandria-engine --extra ml --no-dev

FROM python:3.12-slim-bookworm AS runtime
WORKDIR /app
COPY --from=builder /app /app
# Cache the embedding model inside the image's HOME on first run / pre-download in CI.
ENV PATH="/app/.venv/bin:$PATH" HF_HOME=/data/hf
EXPOSE 8100
CMD ["python", "-m", "engine"]
