import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The SPA talks only to the JSON API with same-origin relative paths
// (e.g. `/graph`). In production FastAPI serves this build at `/`, so the
// paths resolve directly. In dev we proxy the API routes to the FastAPI
// process (apps/api, port 8000) so the same relative paths just work.
//
// IMPORTANT: proxy keys are *prefix* matches. `/node` (the GET /node/{id}
// route) must be written as `/node/` — bare `/node` also matches Vite's own
// `/node_modules/.vite/deps/*.js` requests and forwards React itself to the
// backend (→ 404 → blank page). Keep these as specific as possible.
const API_ROUTES = ["/ingest", "/graph", "/search", "/node/", "/healthz", "/config"];
const API_TARGET = process.env.ALEX_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: Object.fromEntries(
      API_ROUTES.map((route) => [route, { target: API_TARGET, changeOrigin: true }]),
    ),
  },
  build: {
    outDir: "dist",
    // The graph engine + its layout worker are the heavy chunks; keep them
    // split so the React shell paints before the engine bundle arrives.
    chunkSizeWarningLimit: 900,
  },
});
