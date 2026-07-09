import { useEffect, useRef, useState } from "react";

import { INGEST_STAGES } from "../model/ingest";
import type { IngestStage } from "../model/types";

/* A thin progress bar pinned bottom-center while a source is being charted.
   Driven by the ingest job's *real* stage (polled in ActionDock): each stage
   snaps the bar to a fixed milestone and shows its caption (see model/ingest.ts).
   When the job settles (stage → null) the bar completes to 100% and fades.

   A rocket rides the leading edge — the brass bar is its trail — and the caption
   above the rail names the current step. */

const SETTLE_MS = 480; // hold at 100% before fading away

// ── Rocket sprite ───────────────────────────────────────────────────────────
// Swap this single constant for any glyph you like (🛰️, ✦, ➤, 🚀…). For a real
// image sprite, replace the inner <span> in the render with `<img src={…} />`
// or an inline SVG — nothing else needs to change. It's rotated to face right
// (the direction of travel) at render time.
const ROCKET = "🚀";

export function ChartProgress({ stage }: { stage: IngestStage | null }) {
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const [message, setMessage] = useState("Charting…");
  // Mirror `visible` so the falling edge (stage → null) sees the truth without
  // making it an effect dependency.
  const visibleRef = useRef(false);
  visibleRef.current = visible;

  useEffect(() => {
    if (stage) {
      const { label, percent } = INGEST_STAGES[stage];
      setVisible(true);
      setMessage(`${label}…`);
      setProgress(percent);
      return;
    }
    // Job settled. If the bar was up, finish it off; otherwise stay hidden.
    if (!visibleRef.current) return;
    setProgress(100);
    setMessage("Charted");
    const id = setTimeout(() => {
      setVisible(false);
      setProgress(0);
    }, SETTLE_MS);
    return () => clearTimeout(id);
  }, [stage]);

  return (
    <div
      aria-hidden={!visible}
      className="pointer-events-none absolute inset-x-0 bottom-6 z-50 flex justify-center transition-opacity duration-300"
      style={{ opacity: visible ? 1 : 0 }}
    >
      <div className="flex w-[min(420px,68vw)] flex-col items-center gap-1.5">
        {/* Caption above the rail — there's only ~1.5rem below it, too tight for text. */}
        <span
          key={message}
          aria-hidden
          className="animate-fade font-mono text-[0.7rem] tracking-[0.14em] text-vellum-dim uppercase"
        >
          {message}
        </span>

        {/* Rail wrapper is the rocket's positioning context and is NOT clipped,
            so the sprite can ride above the 3px track. */}
        <div className="relative w-full">
          <div
            role="progressbar"
            aria-label="Charting source"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={Math.round(progress)}
            className="h-[3px] w-full overflow-hidden rounded-full border border-line/40 bg-void-2/70"
          >
            <div
              className="h-full rounded-full bg-gradient-to-r from-brass to-brass-bright transition-[width] duration-300 ease-out"
              style={{
                width: `${progress}%`,
                boxShadow:
                  "0 0 8px color-mix(in srgb, var(--color-brass) 65%, transparent)",
              }}
            />
          </div>

          {/* Rocket at the leading edge. Outer span positions on the tip; inner
              span only orients the glyph, so the two transforms never clash. */}
          <span
            aria-hidden
            className="absolute top-1/2 transition-[left] duration-300 ease-out"
            style={{ left: `${progress}%`, transform: "translate(-50%, -50%)" }}
          >
            <span className="block rotate-45 text-[0.8rem] leading-none drop-shadow-[0_0_4px_rgba(232,200,121,0.65)]">
              {ROCKET}
            </span>
          </span>
        </div>
      </div>
    </div>
  );
}
