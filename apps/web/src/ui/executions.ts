/* Pure display formatters for the /executions cost panel. */

export function fmtCost(usd: number | null): string {
  if (usd == null) return "—";
  return usd < 0.01 ? `$${usd.toFixed(4)}` : `$${usd.toFixed(2)}`;
}

export function fmtDuration(ms: number | null): string {
  if (ms == null) return "—";
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

const abbrev = (n: number): string =>
  n >= 1000 ? `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k` : String(n);

export function fmtTokens(
  prompt: number | null,
  completion: number | null,
): string {
  if (!prompt && !completion) return "—";
  return `${abbrev(prompt ?? 0)} → ${abbrev(completion ?? 0)}`;
}
