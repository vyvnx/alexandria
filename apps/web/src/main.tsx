import { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";

import { App } from "./app/App";
import { ExecutionsPage } from "./ui/ExecutionsPage";
import { SourcesPage } from "./ui/SourcesPage";
import "./index.css";

// path routing via the History API: a few pages, no router dependency.
// `/executions` is the cost panel, `/sources` the intake registry; anything
// else is the atlas. Internal links are plain <a href="/...">; the click
// listener below intercepts same-origin clicks so navigation stays client-side
// (the server still serves index.html for these paths directly, see app.py).
function Root() {
  const [path, setPath] = useState(window.location.pathname);
  useEffect(() => {
    const onPop = () => setPath(window.location.pathname);
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement).closest("a");
      if (!a || a.target === "_blank" || a.hasAttribute("download")) return;
      const href = a.getAttribute("href");
      if (!href || !href.startsWith("/") || href.startsWith("//")) return;
      e.preventDefault();
      history.pushState(null, "", href);
      setPath(href);
    }
    window.addEventListener("click", onClick);
    return () => window.removeEventListener("click", onClick);
  }, []);
  if (path.startsWith("/executions")) return <ExecutionsPage />;
  if (path.startsWith("/sources")) return <SourcesPage />;
  return <App />;
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
