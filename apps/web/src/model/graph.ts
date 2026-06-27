/* The one in-memory graph model. `GET /graph` is adapted into a single
   graphology instance that the engine renders and (later) the WASM algo core
   reads. The wire shape is known *only* here (frontend-architecture §8). */

import Graph from "graphology";

import {
  isSemantic,
  type EdgeType,
  type GraphResponse,
  type NodeId,
  type NodeKind,
  type VizConfig,
} from "./types";

/** Just the two sizing knobs from VizConfig; defaulted so callers/tests stay
    simple. The full config is threaded through from `GET /config` at runtime. */
export type SizeConfig = Pick<VizConfig, "star_size_min" | "star_size_max">;
const DEFAULT_SIZE: SizeConfig = { star_size_min: 4, star_size_max: 11 };

/* Celestial convention (design spec §10):
   nodes = glowing stars (colour by kind), edges = brass constellation lines,
   similar-to = rose (predicted/semantic). These read the locked palette. */
const KIND_COLOR: Record<NodeKind, string> = {
  source: "#e8c879", // brass-bright — the things you bring in; the brightest stars
  entity: "#7fe3d6", // starlight — people / orgs / tools
  concept: "#ece4d2", // vellum — ideas
};

const BRASS = "#cba34c";
const ROSE = "#e0897c";

export const kindColor = (kind: NodeKind): string => KIND_COLOR[kind] ?? "#ece4d2";
export const edgeColor = (type: EdgeType): string => (isSemantic(type) ? ROSE : BRASS);

/** Edge key is deterministic so highlight()/picking can reference edges by id. */
export const edgeKey = (src: number, dst: number, type: string): EdgeId_ =>
  `${src}-${dst}-${type}`;
type EdgeId_ = string;

// Deterministic spread on a disc so first paint isn't a single dot; the
// force layout then takes over. Deterministic (not random) keeps reloads stable.
function seedPosition(index: number, total: number): { x: number; y: number } {
  const golden = Math.PI * (3 - Math.sqrt(5)); // golden-angle spiral
  const r = Math.sqrt(index + 0.5) / Math.sqrt(total || 1);
  const a = index * golden;
  return { x: Math.cos(a) * r * 10, y: Math.sin(a) * r * 10 };
}

export interface BuildResult {
  graph: Graph;
}

/** Adapt the API payload into a graphology graph ready for the engine. */
export function buildGraph(data: GraphResponse, cfg: SizeConfig = DEFAULT_SIZE): Graph {
  const graph = new Graph({ multi: true, type: "undirected" });
  const total = data.nodes.length;

  data.nodes.forEach((n, i) => {
    const pos = seedPosition(i, total);
    graph.addNode(String(n.id), {
      label: n.name,
      kind: n.kind,
      color: kindColor(n.kind),
      x: pos.x,
      y: pos.y,
      size: 4, // refined by revisit-weight below
      data: n.data,
    });
  });

  for (const e of data.edges) {
    const src = String(e.src);
    const dst = String(e.dst);
    if (!graph.hasNode(src) || !graph.hasNode(dst)) continue;
    const key = edgeKey(e.src, e.dst, e.type);
    if (graph.hasEdge(key)) continue;
    // alpha scaled by weight so weak similar-to links recede (§9)
    const semantic = isSemantic(e.type);
    const alpha = semantic ? 0.35 + 0.45 * (e.weight ?? 0.5) : 0.7;
    graph.addEdgeWithKey(key, src, dst, {
      etype: e.type,
      weight: e.weight,
      color: withAlpha(edgeColor(e.type), alpha),
      size: semantic ? 0.6 : 1,
    });
  }

  sizeByWeight(graph, cfg);
  return graph;
}

/* Star magnitude ∝ *revisit-weight*: how many distinct sources mention a topic
   (its incident `mentions`/`about` edges), NOT raw degree. Degree conflates the
   revisit signal with `similar-to` (a machine guess), so a once-read concept
   near many others would wrongly outshine a topic read across five sources.
   Sources are excluded from weighting and pinned to the floor — luminance is
   carried by their colour, not size (plan §4). A stand-in until PageRank lands
   in the WASM core. */
export function sizeByWeight(graph: Graph, cfg: SizeConfig = DEFAULT_SIZE): void {
  const { star_size_min: min, star_size_max: max } = cfg;

  graph.forEachNode((node) => graph.setNodeAttribute(node, "weight", 0));
  graph.forEachEdge((_edge, attrs, s, t) => {
    const etype = (attrs as { etype?: string }).etype;
    if (etype !== "mentions" && etype !== "about") return;
    for (const end of [s, t]) {
      if (graph.getNodeAttribute(end, "kind") === "source") continue;
      const w = graph.getNodeAttribute(end, "weight") as number;
      graph.setNodeAttribute(end, "weight", w + 1);
    }
  });

  let maxW = 0;
  graph.forEachNode((node) => {
    if (graph.getNodeAttribute(node, "kind") === "source") return;
    maxW = Math.max(maxW, graph.getNodeAttribute(node, "weight") as number);
  });

  graph.forEachNode((node) => {
    if (graph.getNodeAttribute(node, "kind") === "source") {
      graph.setNodeAttribute(node, "size", min); // fixed-small; weighted by colour
      return;
    }
    const w = graph.getNodeAttribute(node, "weight") as number;
    const t = maxW > 0 ? Math.sqrt(w / maxW) : 0; // sqrt compresses the long tail
    graph.setNodeAttribute(node, "size", min + t * (max - min));
  });
}

function withAlpha(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha.toFixed(3)})`;
}

export type { NodeId };
