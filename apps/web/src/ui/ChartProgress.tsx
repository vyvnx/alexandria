import { useEffect, useRef, useState } from "react";

import { nextTrickle } from "./trickle";

/* A thin progress bar pinned bottom-center while a source is being charted.
   The /ingest request is opaque (one round-trip, no real %), so this is a
   *simulated* indicator: it creeps toward ~90% while `active`, then snaps to
   100% and fades out when charting finishes. See `trickle.ts` for the math.

   A rocket rides the leading edge — the brass bar is its trail — and a rotating
   caption sits above the rail hinting at what's happening. */

const START = 12; // a visible head start the instant charting begins
const TICK_MS = 320; // cadence of the bar's creep
const SETTLE_MS = 480; // hold at 100% before fading away
const MESSAGE_MS = 6000; // how long each caption lingers before the next

// ── Rocket sprite ───────────────────────────────────────────────────────────
// Swap this single constant for any glyph you like (🛰️, ✦, ➤, 🚀…). For a real
// image sprite, replace the inner <span> in the render with `<img src={…} />`
// or an inline SVG — nothing else needs to change. It's rotated to face right
// (the direction of travel) at render time.
const ROCKET = "🚀";

// Rotating loader copy. Index 0 shows the instant charting starts; the rest
// cycle while the bar climbs. Reorder or edit these freely.
const CHARTING_MESSAGES = [
  "Charting…",
  "Mapping the stars…",
  "Plotting constellations…",
  "Triangulating coordinates…",
  "Inking the atlas…",
];

export function ChartProgress({ active }: { active: boolean }) {
  const [progress, setProgress] = useState(0);
  const [visible, setVisible] = useState(false);
  const [msgIndex, setMsgIndex] = useState(0);
  // Read inside the effect without making it a dependency (would restart the
  // creep on every tick). Mirrors `visible` so the falling edge sees the truth.
  const visibleRef = useRef(false);
  visibleRef.current = visible;

  useEffect(() => {
    if (active) {
      setVisible(true);
      setProgress((p) => (p < START ? START : p));
      setMsgIndex(0); // always open on the plain "Charting…"
      const tick = setInterval(
        () => setProgress((p) => nextTrickle(p)),
        TICK_MS,
      );
      const cycle = setInterval(
        () => setMsgIndex((i) => (i + 1) % CHARTING_MESSAGES.length),
        MESSAGE_MS,
      );
      return () => {
        clearInterval(tick);
        clearInterval(cycle);
      };
    }
    // Not charting. If the bar was up, finish it off; otherwise stay hidden.
    if (!visibleRef.current) return;
    setProgress(100);
    const id = setTimeout(() => {
      setVisible(false);
      setProgress(0);
    }, SETTLE_MS);
    return () => clearTimeout(id);
  }, [active]);

  const message = CHARTING_MESSAGES[msgIndex];

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
