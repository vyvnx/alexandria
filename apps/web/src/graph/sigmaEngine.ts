/* Phase 0 GraphEngine: Sigma.js v3 + graphology + ForceAtlas2 in a Worker.
   Carries the design to ~50k nodes (frontend-architecture §19, Phase 0).

   The load-bearing rule lives here: hover, selection, filtering and highlight
   are all imperative internal state applied through Sigma's node/edge reducers
   and a single `refresh()`. None of it round-trips through React, so pan / zoom
   / hover cause ZERO React renders. Phase 1 swaps this file for a cosmos.gl
   implementation of the same interface — no UI change. */

import Graph from "graphology";
import forceAtlas2 from "graphology-layout-forceatlas2";
import FA2Layout from "graphology-layout-forceatlas2/worker";
import type { Attributes } from "graphology-types";
import Sigma from "sigma";
import type { Settings } from "sigma/settings";
import type { EdgeDisplayData, NodeDisplayData } from "sigma/types";

import type { FilterMask } from "../model/filters";
import type { EdgeId, NodeId } from "../model/types";
import { drawHover } from "./labels";
import type {
  EngineEventHandler,
  EngineEventName,
  EngineEvents,
  EngineOptions,
  GraphEngine,
  NodeVisualAttrs,
} from "./engine";

// Dimmed tints applied to everything outside the current focus set, so a
// selection reads as a lit constellation against a receded field.
const MUTED_NODE = "rgba(120, 124, 158, 0.22)";
const MUTED_EDGE = "rgba(80, 86, 120, 0.10)";
const FOCUS_EDGE = "rgba(127, 227, 214, 0.92)"; // starlight — selected neighborhood (§9)

export class SigmaEngine implements GraphEngine {
  private sigma?: Sigma;
  private graph?: Graph;
  private container?: HTMLElement;
  private fa2?: FA2Layout;
  private animate = true;
  private settleTimer?: ReturnType<typeof setTimeout>;

  // imperative interaction state — the whole point of this class
  private hovered: NodeId | null = null;
  private selected: NodeId | null = null;
  private focusNodes = new Set<NodeId>();
  private focusEdges = new Set<EdgeId>();
  private filters: FilterMask | null = null;
  private sizeOverride: Record<NodeId, number> = {};
  private colorOverride: Record<NodeId, string> = {};

  // Loosely typed internal store (string-keyed to avoid generic-index unions);
  // the public `on`/`emit` signatures stay strict, so callers keep full
  // type-safety at the boundary.
  private listeners: Record<string, Array<(payload: never) => void>> = {};

  init(container: HTMLElement, opts?: EngineOptions): void {
    this.container = container;
    this.animate = opts?.animateLayout ?? true;
    this.mount();
  }

  setData(graph: Graph): void {
    this.graph = graph;
    this.mount();
  }

  /** (Re)create the Sigma renderer once both a container and a graph exist. */
  private mount(): void {
    if (!this.container || !this.graph) return;
    if (this.sigma) {
      this.stopLayout();
      this.fa2?.kill();
      this.fa2 = undefined;
      this.sigma.kill();
      this.sigma = undefined;
    }
    this.sigma = new Sigma(this.graph, this.container, this.buildSettings());
    this.wireEvents();
    this.startLayout();
  }

  private buildSettings(): Partial<Settings> {
    return {
      allowInvalidContainer: true,
      // Sigma draws on a transparent canvas; the void gradient shows through.
      defaultNodeColor: "#ece4d2",
      defaultEdgeColor: "#cba34c",
      labelColor: { color: "#ece4d2" },
      labelFont: '"JetBrains Mono", ui-monospace, monospace',
      labelSize: 11,
      labelWeight: "400",
      labelDensity: 0.7,
      labelGridCellSize: 70,
      // LOD label-thinning: only stars rendered above this px size get a name.
      labelRenderedSizeThreshold: 7,
      zIndex: true,
      minCameraRatio: 0.05,
      maxCameraRatio: 14,
      // Keep edges + labels visible while panning/zooming. (These hide-on-move
      // flags are a perf escape hatch for the 100k+ tier — at v1 scale they
      // just make everything but the dots flicker away during interaction.
      // Phase 1 can re-enable them adaptively above a node-count threshold.)
      hideEdgesOnMove: false,
      hideLabelsOnMove: false,
      // Ink-on-parchment hover tag instead of the default white-on-white box.
      defaultDrawNodeHover: drawHover,
      nodeReducer: (node, data) => this.nodeReducer(node, data),
      edgeReducer: (edge, data) => this.edgeReducer(edge, data),
    };
  }

  private nodeReducer(node: string, data: Attributes): Partial<NodeDisplayData> {
    const res: Partial<NodeDisplayData> = { ...data };
    const kind = (data as { kind?: string }).kind;

    if (this.filters && kind && !this.filters.kinds[kind as never]) {
      res.hidden = true;
      return res;
    }
    if (this.sizeOverride[node] != null) res.size = this.sizeOverride[node];
    if (this.colorOverride[node]) res.color = this.colorOverride[node];

    const focused = this.focusNodes.size > 0;
    if (node === this.hovered || node === this.selected) {
      res.highlighted = true;
      res.zIndex = 2;
    } else if (focused) {
      if (this.focusNodes.has(node)) {
        res.zIndex = 1;
      } else {
        res.color = MUTED_NODE;
        res.label = "";
        res.zIndex = 0;
      }
    }
    return res;
  }

  private edgeReducer(edge: string, data: Attributes): Partial<EdgeDisplayData> {
    const res: Partial<EdgeDisplayData> = { ...data };
    const g = this.graph;
    if (!g) return res;
    const etype = (data as { etype?: string }).etype;

    if (this.filters && etype && !this.filters.edgeTypes[etype as never]) {
      res.hidden = true;
      return res;
    }
    const [s, t] = g.extremities(edge);
    if (this.filters) {
      const ks = g.getNodeAttribute(s, "kind") as string;
      const kt = g.getNodeAttribute(t, "kind") as string;
      if (!this.filters.kinds[ks as never] || !this.filters.kinds[kt as never]) {
        res.hidden = true;
        return res;
      }
    }

    if (this.focusNodes.size > 0) {
      const inFocus =
        this.focusEdges.has(edge) || (this.focusNodes.has(s) && this.focusNodes.has(t));
      if (inFocus) {
        res.color = FOCUS_EDGE;
        res.size = (data.size ?? 1) * 1.6;
        res.zIndex = 1;
      } else {
        res.color = MUTED_EDGE;
        res.zIndex = 0;
      }
    }
    return res;
  }

  private wireEvents(): void {
    const s = this.sigma;
    if (!s) return;
    s.on("enterNode", ({ node }) => {
      this.hovered = node;
      this.refresh();
      this.emit("hover", { id: node });
    });
    s.on("leaveNode", () => {
      this.hovered = null;
      this.refresh();
      this.emit("hover", { id: null });
    });
    s.on("clickNode", ({ node }) => {
      this.select(node);
      this.emit("click", { id: node });
    });
    s.on("clickStage", () => {
      this.select(null);
      this.emit("click", { id: null });
    });
    s.getCamera().on("updated", (state) => {
      this.emit("cameraChange", { ratio: state.ratio });
    });
  }

  setFilters(mask: FilterMask): void {
    this.filters = mask;
    this.refresh();
  }

  setNodeAttributes(attrs: NodeVisualAttrs): void {
    if (attrs.size) this.sizeOverride = { ...this.sizeOverride, ...attrs.size };
    if (attrs.color) this.colorOverride = { ...this.colorOverride, ...attrs.color };
    this.refresh();
  }

  select(id: NodeId | null): void {
    this.selected = id;
    this.focusNodes.clear();
    this.focusEdges.clear();
    const g = this.graph;
    if (id && g?.hasNode(id)) {
      this.focusNodes.add(id);
      g.forEachNeighbor(id, (n) => this.focusNodes.add(n));
      g.forEachEdge(id, (edge) => this.focusEdges.add(edge));
    }
    this.refresh();
  }

  highlight(ids: { nodes: NodeId[]; edges: EdgeId[] }): void {
    this.focusNodes = new Set(ids.nodes);
    this.focusEdges = new Set(ids.edges);
    this.selected = ids.nodes[0] ?? null;
    this.refresh();
  }

  focusNode(id: NodeId, opts?: { zoom?: number; durationMs?: number }): void {
    const s = this.sigma;
    if (!s) return;
    const pos = s.getNodeDisplayData(id);
    if (!pos) return;
    s.getCamera().animate(
      { x: pos.x, y: pos.y, ratio: opts?.zoom ?? 0.35 },
      { duration: opts?.durationMs ?? 600 },
    );
  }

  startLayout(): void {
    const g = this.graph;
    if (!g || g.order === 0) return;
    if (this.animate) {
      if (!this.fa2) {
        const settings = forceAtlas2.inferSettings(g);
        this.fa2 = new FA2Layout(g, { settings });
      }
      this.fa2.start();
      // Auto-settle: let it run a budget proportional to size, then stop so we
      // aren't spinning the CPU on a settled graph. Re-runs on new data.
      clearTimeout(this.settleTimer);
      const ms = Math.min(8000, 1500 + g.order * 4);
      this.settleTimer = setTimeout(() => this.stopLayout(), ms);
    } else {
      // Reduced motion: jump straight to a settled layout, no visible churn.
      forceAtlas2.assign(g, { iterations: 200, settings: forceAtlas2.inferSettings(g) });
      this.sigma?.refresh();
    }
  }

  stopLayout(): void {
    clearTimeout(this.settleTimer);
    if (this.fa2?.isRunning()) this.fa2.stop();
  }

  on<E extends EngineEventName>(event: E, cb: EngineEventHandler<E>): void {
    (this.listeners[event] ??= []).push(cb as (payload: never) => void);
  }

  private emit<E extends EngineEventName>(event: E, payload: EngineEvents[E]): void {
    for (const cb of this.listeners[event] ?? []) cb(payload as never);
  }

  private refresh(): void {
    this.sigma?.refresh();
  }

  dispose(): void {
    this.stopLayout();
    this.fa2?.kill();
    this.fa2 = undefined;
    this.sigma?.kill();
    this.sigma = undefined;
    this.listeners = {};
  }
}
