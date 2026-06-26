import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import "./index.css";

// Note: intentionally no <StrictMode>. It double-invokes effects in dev, which
// would create and tear down the WebGL graph engine twice on every mount —
// wasteful and occasionally flaky with GPU contexts. The engine's own lifecycle
// (init/dispose) is correct either way.
const root = document.getElementById("root");
if (root) {
  document.title = "Alexandria · Celestial Atlas";
  createRoot(root).render(<App />);
}
