# apps/web — Alexandria frontend

The knowledge graph as a **celestial atlas**: glowing stars (nodes), brass
constellation lines (edges), starlight-teal for what you select. Vite + React +
TypeScript, with a swappable graph engine behind one interface.

This is **Phase 0** of the frontend architecture spec
(`docs/superpowers/specs/2026-06-25-alexandria-frontend-architecture.md`):
a pragmatic Sigma.js v3 baseline that carries to ~50k nodes. Later phases swap
in a GPU engine (cosmos.gl), a Rust→WASM algorithm core, and LOD streaming —
each behind the same seams, no UI rewrite.

## The one rule

**React renders the chrome; the canvas owns the pixels.** Pan, zoom, and hover
never trigger a React render — they live entirely inside the engine
(`src/graph/sigmaEngine.ts`), applied through Sigma's node/edge reducers. This
single discipline is what keeps free-roam jank-free at any node count. If you
find a `sigma`/`cosmos` import inside a `.tsx` file, that's a bug.

## Layout

```
src/
  app/App.tsx          shell: wires chrome → engine via imperative refs
  graph/
    engine.ts          GraphEngine interface — THE swap seam (§7)
    sigmaEngine.ts     Phase 0 impl: Sigma + ForceAtlas2-in-a-Worker
    createEngine.ts    engine factory + WebGL2 detection (cosmos swaps in here)
  model/
    types.ts           wire types mirroring the JSON API
    graph.ts           GET /graph → one graphology instance (the in-memory truth)
    filters.ts         kind + edge-type masks; legend counts
  api/client.ts        typed fetch client
  hooks/useGraphEngine.ts   the React↔engine bridge (forwards only clicks)
  ui/                  masthead search, AddForm, Legend(=filter), dossier, status
  styles/tokens.css    the locked celestial-atlas palette + type (§10)
```

## Develop

```bash
# from the repo root (npm workspaces + turbo)
npm install
npm run dev --workspace @alexandria/web      # vite on :5173, proxies API → :8000

# run the FastAPI backend in another shell so the proxy has a target
ALEX_LLM=fake uv run python -m alexandria_api
```

Set `ALEX_API_URL` to point the dev proxy at a different backend.

## Build & serve

```bash
npm run build --workspace @alexandria/web    # → apps/web/dist
```

`apps/api` auto-mounts `apps/web/dist` at `/`, so the production backend serves
the SPA directly — no separate web server.

## Test / typecheck

```bash
npm run test --workspace @alexandria/web     # vitest — model adapter + filters
npm run lint --workspace @alexandria/web     # tsc --noEmit
```
