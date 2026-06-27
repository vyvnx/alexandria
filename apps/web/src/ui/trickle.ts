/* Indeterminate-progress math for the charting bar. The /ingest call returns
   only once the whole pipeline finishes, so we can't know a true percentage.
   Instead we *trickle*: each tick closes a fixed fraction of the gap to a
   ceiling below 100%, so the bar moves fast at first and visibly slows as it
   approaches the cap — never arriving. The caller snaps it to 100% on done. */

/** The bar asymptotes toward this without ever reaching it while charting. */
export const TRICKLE_CEILING = 90;

// Fraction of the remaining gap closed per tick. Higher = faster early creep.
const EASE = 0.12;

/** Next bar position given the current one. Monotonic up, capped below the
    ceiling; tolerant of out-of-range input (clamped into [0, ceiling]). */
export function nextTrickle(current: number): number {
  const clamped = Math.min(Math.max(current, 0), TRICKLE_CEILING);
  const next = clamped + (TRICKLE_CEILING - clamped) * EASE;
  // Hold just shy of the ceiling so it never visually "completes" on its own.
  return Math.min(next, TRICKLE_CEILING - 0.05);
}
