# Target-architecture build progress

Tracks implementation of `docs/roadmap/2026-07-09-target-architecture.md`.
**Resume here:** open the active plan, find the first unchecked task, continue.

## Horizons

- [x] **H0 — Headroom** · plan: `docs/superpowers/plans/2026-07-09-target-architecture-h0.md` · done 2026-07-09, branch `feat/target-arch-h0` (147 py + 42 web tests green)
- [ ] **H1 — It reads for you** · plan: `docs/superpowers/plans/2026-07-10-target-architecture-h1.md` ← ACTIVE
- [ ] H2 — It thinks (algo core, insights, digests, GraphRAG) — trigger: ~10⁴ nodes
- [ ] H3 — Billion-tier (Kùzu/Lance/DuckDB, LSH, tile server) — trigger: measured ceilings only

## H0 tasks

- [x] Task 0 — baseline: fixed 2 indentation errors in `pipeline.py`, full suite green (121 py + 34 web), committed pre-existing provider consolidation
- [x] Task 1 — B1: trim `/graph` payload (nodes now `{id, kind, name}`; `WireNode.data` optional; 17 http + 34 web tests green)
- [x] Task 2 — F1: telemetry store + metered proxies (core) — `alexandria_core/telemetry.py`: `TelemetryStore`, `Metered{LLM,Embedder,Vision}`, `add_usage`, `set_current_execution`; config gains `executions_db_path` + `price_{in,out}_per_mtok`; 13 new tests
- [x] Task 3 — F1: surface usage from OpenAI provider — all chat round-trips funnel through `_create`, which reports `resp.usage` via `add_usage`
- [x] Task 4 — F1: wire telemetry into API + `GET /executions` — providers wrapped in `create_app`, ingests bracketed by executions, `.env.example` documents the knobs
- [x] Task 5 — F1: `/executions` web page — hash-routed `ExecutionsPage` (`#/executions`), StatusBar link, formatters unit-tested, verified in the browser against a live fake ingest
- [x] Task 6 — A1: persistent job queue — execution table doubles as the queue (`enqueue`/`claim_next`/`recover`), single daemon worker via lifespan, in-memory jobs dict deleted, `/ingest` contract unchanged. Verified live: stuck `running` job failed as "interrupted by restart" on boot; queued→running→done polling; trimmed `/graph`.

## H1 tasks

- [x] Task 1 — A5: dedup before the LLM — url gate before fetch (unless a new note arrives), sha256 content gate before summarize; `IngestResult.deduped`; lazy `content_hash` column migration
- [x] Task 2 — A3: intake registry (feeds + topics) + HTTP CRUD — `alexandria_core/intake.py` (`IntakeRegistry`: feed/topic/feed_item tables in the graph db), `/feeds` + `/topics` endpoints with 404/409
- [x] Task 3 — A3: feed poller in the worker loop — `poll_feeds` (idle-time pass in the A1 worker), `discover_items` via `trafilatura.feeds`, per-feed failure isolation, `feed_batch_max` backpressure
- [x] Task 4 — A3b: topic-relevance gate — `topic_names` (explicit + interest-pool learned), max-cosine vs `relevance_threshold` (default 0.35) inside `poll_feeds`; filtered items keep their score in `feed_item`
- [x] Task 5 — F2: usage rollups — `TelemetryStore.usage()/spend_since()`, `GET /usage?days=N` (per-day/task/source), summary strip on the executions page
- [x] Task 6 — F3: budgets — `budget_daily_usd`/`budget_monthly_usd` knobs, worker defers queued ingests while over budget, `/usage` reports the budget window state
- [x] Task 7 — A4/F4: per-task routing + budget flip — `engine/router.py` `RoutedLLM` (per-task base URLs, shared instances per URL), over-budget ⇒ fallback provider instead of deferring; empty config byte-identical to before
- [ ] Task 8 — web: `#/sources` management page
- [ ] Task 9 — end-to-end verification

Deferred from H1: F5 (no bulk op to gate), A2b PDF/OCR loader (own plan later), extra A2 loaders (additive behind the loader seam).

## Notes for a fresh session

- Test commands: `uv run pytest -q` (repo root), `pnpm test` in `apps/web`.
- Queue/telemetry share one SQLite `execution` table (see plan header) — no Redis, by design.
- `GET /ingest/{job_id}` response contract is frozen; the web ChartProgress polls it.
