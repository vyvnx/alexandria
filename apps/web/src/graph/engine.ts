/* The single most important contract in the frontend (frontend-architecture
   §7). NO React component imports Sigma or cosmos.gl directly — they talk to
   this interface. Phase 0 implements it with Sigma; Phase 1 swaps in cosmos.gl
   (GPU layout + instanced render) with zero UI changes.

   If you find a Sigma/cosmos call inside a `.tsx` file, that is a bug. */

import type Graph from "graphology";

import type { FilterMask } from "../model/filters";
import type { EdgeId, NodeId } from "../model/types";

export interface EngineOptions {
  /** Run the layout as a visible "settle" animation. Off → lay out instantly
      (used for prefers-reduced-motion). */
  animateLayout?: boolean;
}

/** Per-node visual overrides — size ← PageRank, color ← community/kind.
    Pushed in once the WASM algo core (Phase 2) computes them. */
export interface NodeVisualAttrs {
  size?: Record<NodeId, number>;
  color?: Record<NodeId, string>;
}

export interface EngineEvents {
  hover: { id: NodeId | null };
  /** A node click carries its id; a click on empty sky carries null (deselect). */
  click: { id: NodeId | null };
  cameraChange: { ratio: number };
}
export type EngineEventName = keyof EngineEvents;
export type EngineEventHandler<E extends EngineEventName = EngineEventName> = (
  payload: EngineEvents[E],
) => void;

export interface GraphEngine {
  /** Mount the renderer into a container element. (The spec names a canvas;
      we take the container because Sigma manages its own canvas layers and
      cosmos.gl accepts a div too — keeps the seam honest for both.) */
  init(container: HTMLElement, opts?: EngineOptions): void;

  /** Push the in-memory graphology model. The engine reads positions if
      present and otherwise lays out. */
  setData(graph: Graph): void;

  /** Toggle visibility by attribute mask — NEVER a data reload. */
  setFilters(mask: FilterMask): void;

  /** Per-node visual overrides (size ← PageRank, color ← community/kind). */
  setNodeAttributes(attrs: NodeVisualAttrs): void;

  /** Animate the camera to a node (search-to-focus). */
  focusNode(id: NodeId, opts?: { zoom?: number; durationMs?: number }): void;

  /** Highlight a node + its neighborhood / a path. Empty arrays clear it. */
  highlight(ids: { nodes: NodeId[]; edges: EdgeId[] }): void;

  /** Programmatic selection (mirrors a click), recolours the neighborhood. */
  select(id: NodeId | null): void;

  /** Layout lifecycle (engine runs it on GPU or in a worker). */
  startLayout(): void;
  stopLayout(): void;

  on<E extends EngineEventName>(event: E, cb: EngineEventHandler<E>): void;

  dispose(): void;
}
