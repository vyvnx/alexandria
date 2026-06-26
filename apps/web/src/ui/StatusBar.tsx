import { useEffect, useRef } from "react";

import type { GraphCounts } from "../model/filters";
import type { Health } from "../model/types";

/* The instrument readout. The fps meter writes straight to the DOM from a rAF
   loop — it never calls setState, so the per-frame counter can't itself cause a
   React render (the load-bearing rule applies to our own chrome too). */
export function StatusBar({ counts, health }: { counts: GraphCounts | null; health: Health | null }) {
  const fpsRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    let raf = 0;
    let frames = 0;
    let last = performance.now();
    const loop = (t: number) => {
      frames++;
      if (t - last >= 500) {
        const fps = Math.round((frames * 1000) / (t - last));
        if (fpsRef.current) fpsRef.current.textContent = String(fps);
        frames = 0;
        last = t;
      }
      raf = requestAnimationFrame(loop);
    };
    raf = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf);
  }, []);

  return (
    <div
      role="status"
      className="statusbar-bg pointer-events-none absolute inset-x-0 bottom-0 z-30 flex items-center gap-5 px-4 py-1.5 font-mono text-[0.72rem] tracking-[0.04em] text-vellum-dim"
    >
      <span>
        {counts ? counts.nodes : "—"} stars · {counts ? counts.edges : "—"} lines
      </span>
      <span className="flex-1" />
      {health && (
        <>
          <span>llm: {health.llm}</span>
          <span>vec: {health.vec ? "on" : "off"}</span>
        </>
      )}
      <span className="flex items-center gap-1.5">
        <span className="size-1.5 rounded-full bg-starlight shadow-[0_0_8px_var(--color-starlight)]" />
        <span ref={fpsRef}>60</span> fps
      </span>
    </div>
  );
}
