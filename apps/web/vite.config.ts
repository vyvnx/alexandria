import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// The SPA talks only to the JSON API with same-origin relative paths, all
// under `/api`. In production FastAPI serves this build at `/`, so the paths
// resolve directly. In dev the single `/api` proxy forwards them to the
// FastAPI process (apps/http, port 8000); page paths (`/sources`,
// `/executions`) never collide with it, so Vite serves the SPA shell locally.
const API_TARGET = process.env.ALEX_API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: { "/api": { target: API_TARGET, changeOrigin: true } },
  },
  build: {
    outDir: "dist",
    // The graph engine + its layout worker are the heavy chunks; keep them
    // split so the React shell paints before the engine bundle arrives.
    chunkSizeWarningLimit: 900,
  },
});
