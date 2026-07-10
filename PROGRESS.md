# Target-architecture build progress

Tracks implementation of `docs/roadmap/2026-07-09-target-architecture.md`.
**Resume here:** open the active plan, find the first unchecked task, continue.

## Horizons

- [x] **H0 — Headroom** · plan: `docs/superpowers/plans/2026-07-09-target-architecture-h0.md` · done 2026-07-09, branch `feat/target-arch-h0` (147 py + 42 web tests green)
- [x] **H1 — It reads for you** · plan: `docs/superpowers/plans/2026-07-10-target-architecture-h1.md` · done 2026-07-10, merged to main 2026-07-10 (192 py + 42 web tests green, verified e2e)
- [ ] **H2 — It thinks** · plan: `docs/superpowers/plans/2026-07-10-target-architecture-h2.md` ← ACTIVE (trigger overridden by user: "implement it all")
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
- [x] Task 8 — web: `#/sources` management page — feeds table (poll now / remove / counts) + topic chips, StatusBar link, verified in the browser
- [x] Task 9 — end-to-end verification (2026-07-10, fake LLM + local RSS server):
  - gate open: feed item discovered → queued → pipeline succeeded → searchable in the graph
  - topic added: second feed's item recorded `filtered` with its score, zero LLM calls
  - re-poll: nothing re-ingested (item_seen + url dedup)
  - `/usage` attributes calls per source/task; budget state reported
  - findings fixed during e2e: `trafilatura.feeds` drops local/IP hosts (courlan) → stdlib RSS/Atom parser with `find_feed_urls` fallback; `poll_feeds` was embedding topics on every idle tick → now short-circuits when no feed is due

Deferred from H1: F5 (no bulk op to gate), A2b PDF/OCR loader (own plan later), extra A2 loaders (additive behind the loader seam).

## H2 tasks

- [x] Task 1 — D1: algo core — `alexandria_core/algo.py`: weighted pagerank, deterministic louvain (local-move + aggregation), brandes betweenness (pivot-sampled past 200 nodes), common-neighbor link prediction; 8 exact-structure tests
- [x] Task 2 — D2: structural insights — `insights.py` (interests/communities/bridges/suggestions/trending/contradictions) + `GET /insights`
- [x] Task 3 — D5: pagerank-derived topics — `topic_names` learned half = recurring interests ∪ top-pagerank concepts, capped
- [x] Task 4 — D3: `answer()` provider seam — protocol + fake + openai (cited, context-only prompt) + metered + routed
- [x] Task 5 — D3: GraphRAG — `ask.py` (knn seeds + k-hop expansion → numbered passages, name-match fallback, empty graph short-circuits without llm) + `GET /ask?q=`
- [x] Task 6 — D4: digest — `digest.py` (window counts, pagerank newcomers, trending, resurface-untouched, contradiction count) + `GET /digest?days&narrative` (narrative = opt-in llm call)
- [x] Task 7 — web: `#/insights` page — ask box with citation chips, six insight sections, opt-in digest narrative; StatusBar link (browser check in task 9)
- [x] Task 8 — A2b: digital-PDF ingestion — `load_pdf` (pymupdf text layer), pipeline accepts preloaded docs, `POST /ingest/file` stores uploads content-addressed under `data/uploads/`; scanned pdfs fail with an actionable ocr message (tesseract = user install, still deferred)
- [ ] Task 9 — end-to-end verification

Out of H2 scope (stated triggers/limits): OCR for scanned PDFs (needs the tesseract system binary — user install), Rust→WASM algo core (renderer seam, E-track), H3 storage rungs (measured ceilings only), F5 (no bulk op to gate).

## Notes for a fresh session

- Test commands: `uv run pytest -q` (repo root), `pnpm test` in `apps/web`.
- Queue/telemetry share one SQLite `execution` table (see plan header) — no Redis, by design.
- `GET /ingest/{job_id}` response contract is frozen; the web ChartProgress polls it.
