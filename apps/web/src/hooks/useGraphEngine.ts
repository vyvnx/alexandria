/* The bridge between React (chrome) and the imperative engine (pixels).

   It mounts the engine once into a container and forwards only the *discrete*
   click event back into React (to open the dossier). Hover and camera changes
   are deliberately NOT subscribed to React state — that is what keeps free-roam
   jank-free (frontend-architecture §5, the load-bearing rule). */

import { useEffect, useRef, useState } from "react";

import { createEngine, hasWebGL2 } from "../graph/createEngine";
import type { GraphEngine } from "../graph/engine";
import type { NodeId } from "../model/types";

export function useGraphEngine(
  onSelect: (id: NodeId | null) => void,
  onSettled?: (positions: Record<NodeId, { x: number; y: number }>) => void,
) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const engineRef = useRef<GraphEngine | null>(null);
  const [webgl2] = useState(() => hasWebGL2());

  // Keep the latest callbacks without re-running the mount effect.
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onSettledRef = useRef(onSettled);
  onSettledRef.current = onSettled;

  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;

    const engine = createEngine();
    const reduced =
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    engine.init(container, { animateLayout: !reduced });
    engine.on("click", ({ id }) => onSelectRef.current(id));
    engine.on("settled", ({ positions }) => onSettledRef.current?.(positions));
    engineRef.current = engine;

    return () => {
      engine.dispose();
      engineRef.current = null;
    };
  }, []);

  return { containerRef, engineRef, webgl2 };
}
