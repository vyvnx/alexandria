/* Shared domain + wire types. The *only* place that mirrors the JSON API shape
   (design spec §8, frontend-architecture §15). Keep in sync with apps/api. */

export type NodeId = string; // string app-side; the API uses ints — we stringify
export type EdgeId = string;

export const NODE_KINDS = ["source", "entity", "concept"] as const;
export type NodeKind = (typeof NODE_KINDS)[number];

export const TYPED_EDGES = [
  "mentions",
  "about",
  "uses",
  "extends",
  "contradicts",
  "authored-by",
] as const;
export const SEMANTIC_EDGE = "similar-to";
export const EDGE_TYPES = [...TYPED_EDGES, SEMANTIC_EDGE] as const;
export type EdgeType = (typeof EDGE_TYPES)[number];

/* How much a source pulls into the graph, ordered least → most. The Add panel
   slider walks these stops; "balanced" is the default. Mirrors the backend. */
export const ABSTRACTION_LEVELS = ["abstract", "balanced", "exhaustive"] as const;
export type Abstraction = (typeof ABSTRACTION_LEVELS)[number];

export const isSemantic = (type: string): boolean => type === SEMANTIC_EDGE;

/* ── Wire shapes (exactly what the API returns) ─────────────────────────── */

export interface WireNode {
  id: number;
  kind: NodeKind;
  name: string;
  /** only on `/node/{id}` — `/graph` ships the trimmed shape (roadmap B1) */
  data?: Record<string, unknown>;
}

export interface WireEdge {
  src: number;
  dst: number;
  type: EdgeType;
  weight: number | null;
}

export interface GraphResponse {
  nodes: WireNode[];
  edges: WireEdge[];
}

export interface SearchHit {
  id: number;
  kind: NodeKind;
  name: string;
  score: number | null;
}

export interface NeighborEntry {
  node: WireNode;
  edge: { type: EdgeType; weight: number | null; evidence: string | null };
}

export interface SourceDetail {
  url: string | null;
  author: string | null;
  published_at: string | null;
  summary: string | null;
  my_note: string | null;
  raw_text?: string | null;
}

export interface NodeDetail {
  node: WireNode;
  source: SourceDetail | null;
  neighbors: NeighborEntry[];
}

export interface IngestResult {
  source_id: number;
  title: string;
  summary: string;
  nodes_added: number;
  nodes_reused: number;
  typed_edges_added: number;
  similar_edges_added: number;
  node_ids: number[];
}

/* Progress of a backgrounded ingest, polled from GET /ingest/{job_id}. `stage`
   is the pipeline's current step (see ingest/pipeline.py); the UI maps it to a
   caption + bar fill. `result` lands when status is "done". */
export type IngestStage =
  | "queued"
  | "loading"
  | "visuals"
  | "summarizing"
  | "extracting"
  | "embedding"
  | "resolving"
  | "relating"
  | "linking";

export interface IngestJob {
  status: "running" | "done" | "failed";
  stage: IngestStage;
  result: IngestResult | null;
  error: string | null;
}

export interface Health {
  ok: boolean;
  vec: boolean;
  llm: string;
}

/** Client-facing viz tunables from `GET /config` (backend `Settings`). */
export interface VizConfig {
  star_size_min: number;
  star_size_max: number;
  galaxy_resolution: number;
  min_galaxy_size: number;
  /** Default extraction abstraction; seeds the Add panel slider. */
  extraction_abstraction: Abstraction;
}
