# Target-architecture build progress

Tracks implementation of `docs/roadmap/2026-07-09-target-architecture.md`.
**Resume here:** open the active plan, find the first unchecked task, continue.

## Horizons

- [ ] **H0 — Headroom** · plan: `docs/superpowers/plans/2026-07-09-target-architecture-h0.md` ← ACTIVE
- [ ] H1 — It reads for you (source registry, loaders, relevance filter, budgets/routing) — plan to be written when H0 lands
- [ ] H2 — It thinks (algo core, insights, digests, GraphRAG) — trigger: ~10⁴ nodes
- [ ] H3 — Billion-tier (Kùzu/Lance/DuckDB, LSH, tile server) — trigger: measured ceilings only

## H0 tasks

- [x] Task 0 — baseline: fixed 2 indentation errors in `pipeline.py`, full suite green (121 py + 34 web), committed pre-existing provider consolidation
- [x] Task 1 — B1: trim `/graph` payload (nodes now `{id, kind, name}`; `WireNode.data` optional; 17 http + 34 web tests green)
- [x] Task 2 — F1: telemetry store + metered proxies (core) — `alexandria_core/telemetry.py`: `TelemetryStore`, `Metered{LLM,Embedder,Vision}`, `add_usage`, `set_current_execution`; config gains `executions_db_path` + `price_{in,out}_per_mtok`; 13 new tests
- [x] Task 3 — F1: surface usage from OpenAI provider — all chat round-trips funnel through `_create`, which reports `resp.usage` via `add_usage`
- [x] Task 4 — F1: wire telemetry into API + `GET /executions` — providers wrapped in `create_app`, ingests bracketed by executions, `.env.example` documents the knobs
- [ ] Task 5 — F1: `/executions` web page
- [ ] Task 6 — A1: persistent job queue

## Notes for a fresh session

- Test commands: `uv run pytest -q` (repo root), `pnpm test` in `apps/web`.
- Queue/telemetry share one SQLite `execution` table (see plan header) — no Redis, by design.
- `GET /ingest/{job_id}` response contract is frozen; the web ChartProgress polls it.
