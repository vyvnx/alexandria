import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { ExecutionsPage } from "./ui/ExecutionsPage";
import "./index.css";

// hash routing: two pages, no router dependency. `#/executions` is the cost
// panel; anything else is the atlas.
function Root() {
  const [hash, setHash] = useState(window.location.hash);
  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash.startsWith("#/executions") ? <ExecutionsPage /> : <App />;
}

// Note: intentionally no <StrictMode>. It double-invokes effects in dev, which
// would create and tear down the WebGL graph engine twice on every mount —
// wasteful and occasionally flaky with GPU contexts. The engine's own lifecycle
// (init/dispose) is correct either way.
const root = document.getElementById("root");
if (root) {
  document.title = "Alexandria";
  createRoot(root).render(<Root />);
}
