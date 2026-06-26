/* Filtering is a *model* concern: graphology (here) decides which primitives
   are visible; the engine just toggles their visibility as a GPU/attribute
   mask — never a data reload (frontend-architecture §9, §12). */

import {
  EDGE_TYPES,
  NODE_KINDS,
  type EdgeType,
  type GraphResponse,
  type NodeKind,
} from "./types";

export interface FilterMask {
  kinds: Record<NodeKind, boolean>;
  edgeTypes: Record<EdgeType, boolean>;
}

export function defaultMask(): FilterMask {
  return {
    kinds: Object.fromEntries(NODE_KINDS.map((k) => [k, true])) as Record<NodeKind, boolean>,
    edgeTypes: Object.fromEntries(EDGE_TYPES.map((t) => [t, true])) as Record<EdgeType, boolean>,
  };
}

export function toggleKind(mask: FilterMask, kind: NodeKind): FilterMask {
  return { ...mask, kinds: { ...mask.kinds, [kind]: !mask.kinds[kind] } };
}

export function toggleEdgeType(mask: FilterMask, type: EdgeType): FilterMask {
  return { ...mask, edgeTypes: { ...mask.edgeTypes, [type]: !mask.edgeTypes[type] } };
}

export interface GraphCounts {
  kinds: Record<NodeKind, number>;
  edgeTypes: Record<EdgeType, number>;
  nodes: number;
  edges: number;
}

/** Tally nodes-by-kind and edges-by-type so the legend can show magnitudes. */
export function countGraph(data: GraphResponse): GraphCounts {
  const kinds = Object.fromEntries(NODE_KINDS.map((k) => [k, 0])) as Record<NodeKind, number>;
  const edgeTypes = Object.fromEntries(EDGE_TYPES.map((t) => [t, 0])) as Record<EdgeType, number>;
  for (const n of data.nodes) if (n.kind in kinds) kinds[n.kind]++;
  for (const e of data.edges) if (e.type in edgeTypes) edgeTypes[e.type]++;
  return { kinds, edgeTypes, nodes: data.nodes.length, edges: data.edges.length };
}
