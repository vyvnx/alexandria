/* Typed fetch client. Talks only to the JSON API over same-origin relative
   paths (vite proxies these to FastAPI in dev; FastAPI serves us at `/` in
   prod). Every call funnels through `request` so error handling is uniform. */

import type {
  Abstraction,
  AskResult,
  Digest,
  ExecutionRow,
  FeedRow,
  Insights,
  GraphResponse,
  Health,
  IngestJob,
  NodeDetail,
  SearchHit,
  TopicRow,
  UsageSummary,
  VizConfig,
} from "../model/types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(path, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    // Network/connection failure — the backend isn't reachable.
    throw new ApiError("Can't reach Alexandria. Is the backend running?", 0);
  }
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    const msg =
      (detail && typeof detail === "object" && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : null) ?? `Request failed (${res.status}).`;
    throw new ApiError(msg, res.status);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/healthz"),

  /** Viz tunables (star sizing + galaxy clustering knobs) from the backend. */
  config: () => request<VizConfig>("/config"),

  /** Full graph, or a k-hop neighborhood around one node. */
  graph: (opts?: { nodeId?: number; k?: number }) => {
    const params = new URLSearchParams();
    if (opts?.nodeId != null) params.set("node_id", String(opts.nodeId));
    if (opts?.k != null) params.set("k", String(opts.k));
    const qs = params.toString();
    return request<GraphResponse>(`/graph${qs ? `?${qs}` : ""}`);
  },

  node: (id: number) => request<NodeDetail>(`/node/${id}`),

  /** Dismiss a node as "not interested": deletes it and suppresses the topic
      in future ingests. */
  dismissNode: (id: number) =>
    request<{ dismissed: string }>(`/node/${id}/dismiss`, { method: "POST" }),

  search: (q: string) => request<SearchHit[]>(`/search?q=${encodeURIComponent(q)}`),

  /** Kick off an ingest; returns a job id to poll with `ingestStatus`. */
  ingest: (body: { url?: string; note?: string; abstraction?: Abstraction; visual?: boolean }) =>
    request<{ job_id: string }>("/ingest", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  /** Current stage/status of a running ingest job. */
  ingestStatus: (jobId: string) => request<IngestJob>(`/ingest/${jobId}`),

  /** Ingest executions ledger (cost/status), newest first. */
  executions: () => request<ExecutionRow[]>("/executions"),

  /** Cost rollups for the summary strip. */
  usage: (days = 30) => request<UsageSummary>(`/usage?days=${days}`),

  /** Intelligence layer (D2–D4). */
  insights: () => request<Insights>("/insights"),
  ask: (q: string) => request<AskResult>(`/ask?q=${encodeURIComponent(q)}`),
  digest: (narrative = false) =>
    request<Digest>(`/digest${narrative ? "?narrative=true" : ""}`),

  /** Curated intake registry (A3). */
  feeds: () => request<FeedRow[]>("/feeds"),
  addFeed: (url: string, cadence_minutes = 60) =>
    request<{ id: number }>("/feeds", {
      method: "POST",
      body: JSON.stringify({ url, cadence_minutes }),
    }),
  removeFeed: (id: number) =>
    request<{ removed: number }>(`/feeds/${id}`, { method: "DELETE" }),
  pollFeed: (id: number) =>
    request<{ polling: number }>(`/feeds/${id}/poll`, { method: "POST" }),
  topics: () => request<TopicRow[]>("/topics"),
  addTopic: (name: string) =>
    request<{ id: number }>("/topics", {
      method: "POST",
      body: JSON.stringify({ name }),
    }),
  removeTopic: (id: number) =>
    request<{ removed: number }>(`/topics/${id}`, { method: "DELETE" }),
};
