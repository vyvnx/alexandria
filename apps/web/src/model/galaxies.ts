/* Discovered galaxies: topics grouped into communities by the graph's *own*
   edges (frontend Louvain), drawn later as dashed boundaries (engine overlay).
   Clustering reads the same edges the force layout reads, so a hull wraps the
   region the eye sees clumping. Membership + name + colour are computed once per
   graph build (they depend on edges/weights, not positions) — only the hull
   geometry is recomputed per frame. See the topic-weight-galaxies plan §2–§3. */

import type Graph from "graphology";
import louvain from "graphology-communities-louvain";

import type { NodeId, VizConfig } from "./types";

export interface Galaxy {
  id: string;
  name: string;
  color: string;
  members: NodeId[];
}

export interface GalaxyMap {
  byId: Galaxy[];
  nodeToGalaxy: Record<NodeId, string>;
}

/** The two clustering knobs from VizConfig; defaulted for callers/tests. */
export type GalaxyConfig = Pick<VizConfig, "galaxy_resolution" | "min_galaxy_size">;
const DEFAULT_GALAXY: GalaxyConfig = { galaxy_resolution: 1.0, min_galaxy_size: 3 };

/* Stroke palette for zone boundaries — soft, atlas-map tints that read as
   faint outlines and stay clear of the kind hues (brass/starlight/vellum), so
   colour keeps meaning `kind` while the dashed outline means `zone`. */
const GALAXY_PALETTE = [
  "#9db4d8", // faint azure
  "#c9a36a", // muted brass-gold
  "#b58fb0", // dusty mauve
  "#7fb8a6", // sea-glass teal
  "#cf9b86", // clay rose
  "#a6a2cc", // periwinkle
  "#b9c08a", // sage
];

/* A fixed seed makes Louvain deterministic, so community membership, ids,
   colours, and names are stable across reloads (plan §3, "Determinism"). */
const SEED = 0x1a2b3c4d;

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/** Group nodes into galaxies via Louvain over `weight`-weighted edges. Typed
    edges (weight `null`) count as full-strength structural links; `similar-to`
    keeps its cosine. Communities below `min_galaxy_size` draw no hull and their
    nodes stay lone stars (absent from `nodeToGalaxy`). */
export function detectGalaxies(graph: Graph, cfg: GalaxyConfig = DEFAULT_GALAXY): GalaxyMap {
  const empty: GalaxyMap = { byId: [], nodeToGalaxy: {} };
  if (graph.order === 0) return empty;

  let mapping: Record<string, number>;
  try {
    mapping = louvain(graph, {
      resolution: cfg.galaxy_resolution,
      rng: mulberry32(SEED),
      getEdgeWeight: (_edge, attr) => {
        const w = (attr as { weight?: number | null }).weight;
        return typeof w === "number" ? w : 1;
      },
    });
  } catch {
    return empty; // a degenerate graph Louvain can't process — no zones, no crash
  }

  const groups = new Map<number, NodeId[]>();
  for (const [node, community] of Object.entries(mapping)) {
    const arr = groups.get(community);
    if (arr) arr.push(node);
    else groups.set(community, [node]);
  }

  // Drop sub-threshold communities; sort everything by smallest member id so
  // ids and palette colours are assigned in a stable order across reloads.
  const surviving = [...groups.values()]
    .filter((members) => members.length >= cfg.min_galaxy_size)
    .map((members) => members.slice().sort((a, b) => Number(a) - Number(b)))
    .sort((a, b) => Number(a[0]) - Number(b[0]));

  const byId: Galaxy[] = [];
  const nodeToGalaxy: Record<NodeId, string> = {};
  surviving.forEach((members, i) => {
    const id = `galaxy-${i}`;
    byId.push({
      id,
      name: nameGalaxy(graph, members),
      color: GALAXY_PALETTE[i % GALAXY_PALETTE.length],
      members,
    });
    for (const m of members) nodeToGalaxy[m] = id;
  });

  return { byId, nodeToGalaxy };
}

/** A galaxy's name is its single most-revisited member of any kind — concept or
    entity — but never a `source` (sources are the things you bring in, not the
    area they map to). A clean future swap point for LLM umbrella-labelling. */
export function nameGalaxy(graph: Graph, members: NodeId[]): string {
  const weightOf = (n: NodeId) => (graph.getNodeAttribute(n, "weight") as number) ?? 0;
  const kindOf = (n: NodeId) => graph.getNodeAttribute(n, "kind") as string;
  const labelOf = (n: NodeId) => (graph.getNodeAttribute(n, "label") as string) ?? "";

  // members arrive numerically sorted and V8's sort is stable, so equal-weight
  // ties resolve deterministically.
  const ranked = members
    .filter((n) => kindOf(n) !== "source")
    .sort((a, b) => weightOf(b) - weightOf(a));

  // Degenerate clusters (sources only) still get a name so the zone reads.
  return labelOf(ranked[0] ?? members[0]);
}
