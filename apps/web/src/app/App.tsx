import { AlertTriangle, Sparkles, Telescope } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api } from "../api/client";
import alexandriaIcon from "../assets/alexandria-icon.png";
import { useGraphEngine } from "../hooks/useGraphEngine";
import { detectGalaxies } from "../model/galaxies";
import { buildGraph } from "../model/graph";
import {
  countGraph,
  defaultMask,
  toggleEdgeType,
  toggleKind,
  toggleZones,
  type FilterMask,
  type GraphCounts,
} from "../model/filters";
import type {
  EdgeType,
  GraphResponse,
  Health,
  IngestResult,
  NodeDetail,
  NodeId,
  NodeKind,
  VizConfig,
} from "../model/types";

// Viz tunables fall back to the plan's defaults if GET /config is unreachable,
// so the atlas still sizes stars and clusters galaxies sensibly offline.
const DEFAULT_CONFIG: VizConfig = {
  star_size_min: 4,
  star_size_max: 11,
  galaxy_resolution: 1.0,
  min_galaxy_size: 3,
  extraction_abstraction: "balanced",
};
import { ActionDock } from "../ui/ActionDock";
import { ChartProgress } from "../ui/ChartProgress";
import { Legend } from "../ui/Legend";
import { NodeInspector } from "../ui/NodeInspector";
import { StatusBar } from "../ui/StatusBar";

export function App() {
  const [graphData, setGraphData] = useState<GraphResponse | null>(null);
  const [counts, setCounts] = useState<GraphCounts | null>(null);
  const [health, setHealth] = useState<Health | null>(null);
  const [config, setConfig] = useState<VizConfig>(DEFAULT_CONFIG);
  const [mask, setMask] = useState<FilterMask>(defaultMask);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<NodeDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [toast, setToast] = useState<{ msg: string; error: boolean } | null>(null);

  const maskRef = useRef(mask);
  const pendingFocus = useRef<number | null>(null);

  const { containerRef, engineRef, webgl2 } = useGraphEngine((id: NodeId | null) => {
    setSelectedId(id == null ? null : Number(id));
  });

  useEffect(() => {
    api.health().then(setHealth).catch(() => undefined);
    api.config().then(setConfig).catch(() => undefined); // keep DEFAULT_CONFIG on failure
    void loadGraph();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadGraph() {
    try {
      const data = await api.graph();
      setGraphData(data);
      setCounts(countGraph(data));
    } catch (err) {
      setToast({ msg: err instanceof Error ? err.message : "Couldn't load the atlas.", error: true });
    }
  }

  // Rebuild the graphology model and hand it to the engine whenever data (or the
  // viz config, which may arrive after first paint) changes. Sizing + galaxy
  // membership are computed here, in the browser, so the hulls match the layout.
  useEffect(() => {
    if (!graphData) return;
    const g = buildGraph(graphData, config);
    engineRef.current?.setData(g);
    const galaxies = detectGalaxies(g, config);
    engineRef.current?.setGalaxies(galaxies);
    engineRef.current?.setFilters(maskRef.current);
    setCounts((c) => (c ? { ...c, galaxies: galaxies.byId.length } : c));
    if (pendingFocus.current != null) {
      const id = String(pendingFocus.current);
      pendingFocus.current = null;
      const timer = setTimeout(() => {
        engineRef.current?.focusNode(id, { zoom: 0.4 });
        engineRef.current?.select(id);
      }, 220);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData, config]);

  // Filters are a visibility mask on the engine — never a data reload.
  useEffect(() => {
    maskRef.current = mask;
    engineRef.current?.setFilters(mask);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mask]);

  // Selection → fetch the dossier detail.
  useEffect(() => {
    if (selectedId == null) {
      setDetail(null);
      return;
    }
    let cancelled = false;
    setDetailLoading(true);
    api
      .node(selectedId)
      .then((d) => !cancelled && setDetail(d))
      .catch(() => !cancelled && setDetail(null))
      .finally(() => !cancelled && setDetailLoading(false));
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4500);
    return () => clearTimeout(t);
  }, [toast]);

  function focusAndSelect(id: number) {
    setSelectedId(id);
    const sid = String(id);
    engineRef.current?.focusNode(sid, { zoom: 0.4 });
    engineRef.current?.select(sid);
  }

  async function handleIngested(r: IngestResult) {
    const lines = r.typed_edges_added + r.similar_edges_added;
    setToast({
      msg: `Charted “${r.title}”. +${r.nodes_added} stars · ${r.nodes_reused} reused · +${lines} lines`,
      error: false,
    });
    pendingFocus.current = r.source_id;
    await loadGraph();
  }

  function closeDossier() {
    setSelectedId(null);
    engineRef.current?.select(null);
  }

  const isEmpty = !!graphData && counts?.nodes === 0;

  return (
    <div className="app-bg relative h-full w-full overflow-hidden">
      <div className="atlas-grid pointer-events-none absolute inset-0 z-0" />
      <div ref={containerRef} className="absolute inset-0 z-0" />

      <header className="masthead-bg pointer-events-none absolute inset-x-0 top-0 z-30 flex items-center gap-3 px-[1.1rem] py-[0.85rem]">
        <div className="pointer-events-auto flex items-baseline gap-2 select-none">
          <img
            src={alexandriaIcon}
            alt="Alexandria icon"
            className="h-[2.35rem] w-[2.35rem] -translate-y-[0.05rem] self-center drop-shadow-[0_0_0.4rem_rgba(181,153,92,0.6)]"
          />
          <span className="font-display text-[clamp(1.6rem,1.1rem+1.6vw,2.4rem)] font-medium tracking-[0.18em] text-vellum">
            Alexandria
          </span>
          <span className="hidden font-mono text-[0.72rem] tracking-[0.04em] text-vellum-dim md:inline">
            a celestial index of what you've read
          </span>
        </div>
        <span className="flex-1" />
      </header>

      {isEmpty && (
        <div className="pointer-events-none absolute inset-0 z-10 grid place-items-center text-center">
          <div className="max-w-[30ch]">
            <Telescope className="mx-auto size-9 text-brass-bright" strokeWidth={1.5} />
            <h2 className="font-display mt-2.5 text-[1.85rem] font-medium">The sky is empty</h2>
            <p className="mt-1 text-vellum-dim">
              Chart your first source to begin the atlas — paste a link and your thoughts on it.
            </p>
          </div>
        </div>
      )}

      <Legend
        mask={mask}
        counts={counts}
        onToggleKind={(k: NodeKind) => setMask((m) => toggleKind(m, k))}
        onToggleEdgeType={(t: EdgeType) => setMask((m) => toggleEdgeType(m, t))}
        onToggleZones={() => setMask((m) => toggleZones(m))}
      />

      <ActionDock
        onPick={focusAndSelect}
        onIngested={handleIngested}
        onBusyChange={setIngesting}
        onIngestError={(msg) => setToast({ msg, error: true })}
        defaultAbstraction={config.extraction_abstraction}
      />

      <ChartProgress active={ingesting} />

      <NodeInspector
        detail={detail}
        loading={detailLoading}
        onClose={closeDossier}
        onPickNeighbor={focusAndSelect}
      />

      {!webgl2 && (
        <Toast error>WebGL2 isn't available — the graph may not render. Try a current browser.</Toast>
      )}
      {toast && (
        <Toast error={toast.error}>{toast.msg}</Toast>
      )}

      <StatusBar counts={counts} health={health} />
    </div>
  );
}

function Toast({ error, children }: { error?: boolean; children: React.ReactNode }) {
  const Icon = error ? AlertTriangle : Sparkles;
  return (
    <div
      role={error ? "alert" : "status"}
      className={`panel animate-rise absolute bottom-[2.6rem] left-1/2 z-50 flex max-w-[80vw] -translate-x-1/2 items-center gap-2 px-3.5 py-2.5 text-[0.82rem] ${
        error ? "border-rose/55" : ""
      }`}
    >
      <Icon className={`size-4 flex-none ${error ? "text-rose" : "text-brass-bright"}`} />
      {children}
    </div>
  );
}
