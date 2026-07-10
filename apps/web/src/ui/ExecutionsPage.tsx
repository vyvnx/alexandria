import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { ExecutionRow, UsageSummary } from "../model/types";
import { fmtCost, fmtDuration, fmtTokens } from "./executions";

/* The /executions cost panel (roadmap F1): a plain table straight off the
   ledger — source, status, duration, tokens, cost — newest first. No charts,
   filters, or pagination until this proves insufficient. */
export function ExecutionsPage() {
  const [rows, setRows] = useState<ExecutionRow[] | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .executions()
      .then(setRows)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Couldn't load executions."),
      );
    api
      .usage()
      .then(setUsage)
      .catch(() => undefined); // the table still stands without the strip
  }, []);

  return (
    <div className="app-bg h-full w-full overflow-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-5 flex items-baseline gap-4">
          <h1 className="font-display text-[1.6rem] font-medium">Executions</h1>
          <a
            href="#"
            className="text-[0.82rem] text-vellum-dim hover:text-vellum"
          >
            ← back to the atlas
          </a>
        </header>

        {usage && (
          <p className="mb-4 font-mono text-[0.78rem] text-vellum-dim">
            last {usage.days} days:{" "}
            {usage.total_cost_usd > 0 ? fmtCost(usage.total_cost_usd) : "$0"} ·{" "}
            {usage.total_calls} calls ·{" "}
            {fmtTokens(usage.prompt_tokens, usage.completion_tokens)} tokens
          </p>
        )}

        {error && (
          <p role="alert" className="text-rose">
            {error}
          </p>
        )}
        {rows && rows.length === 0 && (
          <p className="text-vellum-dim">
            Nothing charted yet — ingests will land here with their cost.
          </p>
        )}

        {rows && rows.length > 0 && (
          <table className="w-full border-collapse font-mono text-[0.78rem]">
            <thead>
              <tr className="border-b border-vellum-dim/30 text-left text-vellum-dim">
                <th className="py-2 pr-4 font-normal">source</th>
                <th className="py-2 pr-4 font-normal">status</th>
                <th className="py-2 pr-4 font-normal">duration</th>
                <th className="py-2 pr-4 font-normal">tokens in → out</th>
                <th className="py-2 pr-4 font-normal">cost</th>
                <th className="py-2 font-normal">queued</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-b border-vellum-dim/10">
                  <td
                    className="max-w-[24rem] truncate py-2 pr-4"
                    title={r.source}
                  >
                    {r.source}
                  </td>
                  <td
                    className={`py-2 pr-4 ${
                      r.status === "failed"
                        ? "text-rose"
                        : r.status === "succeeded"
                          ? "text-starlight"
                          : "text-vellum-dim"
                    }`}
                  >
                    {r.status === "running" || r.status === "queued"
                      ? `${r.status} · ${r.stage}`
                      : r.status}
                  </td>
                  <td className="py-2 pr-4">{fmtDuration(r.duration_ms)}</td>
                  <td className="py-2 pr-4">
                    {fmtTokens(r.prompt_tokens, r.completion_tokens)}
                  </td>
                  <td className="py-2 pr-4">{fmtCost(r.cost_usd)}</td>
                  <td className="py-2 text-vellum-dim">
                    {new Date(r.queued_at).toLocaleString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}
