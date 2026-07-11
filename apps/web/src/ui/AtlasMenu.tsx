import { Layers, Sparkles } from "lucide-react";
import { motion } from "motion/react";
import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { FilterMask, GraphCounts } from "../model/filters";
import type { AskResult, EdgeType, Insights, NodeKind } from "../model/types";
import { Legend } from "./Legend";

type TabId = "legend" | "insights";
const TABS: { id: TabId; label: string; Icon: typeof Layers }[] = [
  { id: "legend", label: "Legend", Icon: Layers },
  { id: "insights", label: "Insights", Icon: Sparkles },
];

/* The atlas menu — a floating spine dock at the chart's edge. Clicking a
   spine opens the drawer on that tab (legend filters or the insights tab);
   clicking the active spine again closes it. */
export function AtlasMenu({
  mask,
  counts,
  onToggleKind,
  onToggleEdgeType,
  onToggleZones,
}: {
  mask: FilterMask;
  counts: GraphCounts | null;
  onToggleKind: (k: NodeKind) => void;
  onToggleEdgeType: (t: EdgeType) => void;
  onToggleZones: () => void;
}) {
  const [open, setOpen] = useState(true);
  const [tab, setTab] = useState<TabId>("legend");
  // insights mounts on first visit and stays alive after, so switching
  // between tabs never refetches
  const [insightsVisited, setInsightsVisited] = useState(false);

  function spineClick(t: TabId) {
    if (open && tab === t) {
      setOpen(false);
    } else {
      setTab(t);
      setOpen(true);
      if (t === "insights") setInsightsVisited(true);
    }
  }

  return (
    <div className="pointer-events-auto absolute right-4 top-[4.75rem] z-30 flex items-start gap-2 max-md:hidden">
      <motion.div
        aria-hidden={!open}
        initial={false}
        animate={open ? { opacity: 1, x: 0 } : { opacity: 0, x: 10 }}
        transition={{ duration: 0.24, ease: [0.22, 0.61, 0.36, 1] }}
        style={{ pointerEvents: open ? "auto" : "none" }}
        className="panel "
      >
        <div className="flex items-center gap-2 px-3 pt-2.5 text-[0.64rem] uppercase tracking-[0.2em] text-vellum-dim/80">
          <motion.span
            key={tab}
            initial={{ opacity: 0, y: 3 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18, ease: "easeOut" }}
            className="font-mono"
          >
            {tab}
          </motion.span>
          <div className="h-px flex-1 bg-line/60" aria-hidden />
        </div>
        {/* both panes stay mounted (insights keeps its data) stacked in one
            grid cell, so the crossfade never reflows the drawer */}
        {/* pr clears the 6px scrollbar so row values never sit under it */}
        <div className="thin-scrollbar grid max-h-[calc(100vh-11rem)] items-start overflow-y-auto py-2.5 pl-3 pr-4">
          <TabPane active={tab === "legend"}>
            <Legend
              mask={mask}
              counts={counts}
              onToggleKind={onToggleKind}
              onToggleEdgeType={onToggleEdgeType}
              onToggleZones={onToggleZones}
            />
          </TabPane>
          {insightsVisited && (
            <TabPane active={tab === "insights"}>
              <InsightsTab />
            </TabPane>
          )}
        </div>
      </motion.div>

      <div className="flex flex-col gap-1 rounded-lg border border-line/60 bg-void-2/80 p-1 shadow-[0_18px_40px_-30px_#000] backdrop-blur">
        {TABS.map(({ id, label, Icon }) => {
          const on = open && tab === id;
          return (
            <button
              key={id}
              type="button"
              title={label}
              aria-pressed={on}
              onClick={() => spineClick(id)}
              className={`spine relative focus-visible:ring-2 focus-visible:ring-starlight focus-visible:outline-none ${
                on ? "spine-on" : ""
              }`}
            >
              {on && (
                <motion.span
                  layoutId="spine-active"
                  transition={{ type: "spring", stiffness: 450, damping: 38 }}
                  className="absolute inset-0 rounded-md bg-brass/15 shadow-[inset_2px_0_0_0_var(--color-brass),0_0_12px_-6px_var(--color-brass)]"
                  aria-hidden
                />
              )}
              <Icon
                className="relative size-[13px] flex-none"
                strokeWidth={1.6}
              />
              <span className="relative">{label}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* One drawer pane. Panes share a grid cell and never unmount — switching tabs
   slides/fades the incoming pane in and display:none's the outgoing one after
   its fade, so pane state (fetched insights, a typed question) survives. */
function TabPane({
  active,
  children,
}: {
  active: boolean;
  children: React.ReactNode;
}) {
  return (
    <motion.div
      initial={false}
      animate={
        active
          ? {
              opacity: 1,
              x: 0,
              display: "block",
              transition: { duration: 0.2, delay: 0.06, ease: "easeOut" },
            }
          : {
              opacity: 0,
              x: 6,
              transition: { duration: 0.12, ease: "easeIn" },
              transitionEnd: { display: "none" },
            }
      }
      className="col-start-1 row-start-1"
    >
      {children}
    </motion.div>
  );
}

/* The intelligence tab (D2–D3): ask the graph a question, and read what it
   thinks matters — interests, trends, communities, bridges, undrawn
   connections, contradictions. Insights load once, on first open. */
function InsightsTab() {
  const [insights, setInsights] = useState<Insights | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AskResult | null>(null);

  useEffect(() => {
    api
      .insights()
      .then(setInsights)
      .catch((e) =>
        setError(e instanceof Error ? e.message : "Couldn't load insights."),
      );
  }, []);

  async function submitAsk(e: React.FormEvent) {
    e.preventDefault();
    if (!question.trim() || asking) return;
    setAsking(true);
    setAnswer(null);
    try {
      setAnswer(await api.ask(question.trim()));
    } catch (err) {
      setError(err instanceof Error ? err.message : "The graph didn't answer.");
    } finally {
      setAsking(false);
    }
  }

  return (
    <div className="flex flex-col gap-2.5">
      <form className="flex gap-1.5" onSubmit={submitAsk}>
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="what connects x to y?"
          aria-label="Ask the graph"
          className="control min-w-0 px-2 py-1 font-mono text-[0.72rem]"
        />
        <button
          type="submit"
          disabled={asking}
          className="btn px-2.5 py-1 text-[0.72rem]"
        >
          {asking ? "…" : "ask"}
        </button>
      </form>
      {error && (
        <p role="alert" className="text-[0.74rem] text-rose">
          {error}
        </p>
      )}
      {answer && (
        <div className="text-[0.78rem]">
          <p>{answer.answer}</p>
          {answer.citations.length > 0 && (
            <p className="mt-1 font-mono text-[0.66rem] text-vellum-dim">
              {answer.citations.map((c) => `[${c.n}] ${c.name}`).join(" · ")}
            </p>
          )}
        </div>
      )}
      {insights && (
        <>
          <InsightSection title="Strongest interests">
            {insights.strongest_interests.map((n, i) => (
              <InsightRow
                key={n.id}
                rank={i + 1}
                left={n.name}
                right={n.score.toFixed(4)}
              />
            ))}
          </InsightSection>
          <InsightSection title="Circling lately">
            {insights.trending.map((t) => (
              <InsightRow
                key={t.name}
                left={t.name}
                right={t.weight.toFixed(2)}
              />
            ))}
          </InsightSection>
          <InsightSection title="Emergent communities">
            {insights.communities.map((c) => (
              <InsightRow key={c.id} left={c.label} right={`${c.size} nodes`} />
            ))}
          </InsightSection>
          <InsightSection title="Serendipity bridges">
            {insights.bridges.map((n) => (
              <InsightRow key={n.id} left={n.name} right={n.score.toFixed(2)} />
            ))}
          </InsightSection>
          <InsightSection title="Connections you haven't drawn">
            {insights.suggested_connections.map((s, i) => (
              <InsightRow
                key={i}
                left={`${s.a.name} ↔ ${s.b.name}`}
                right={`${s.common} shared`}
              />
            ))}
          </InsightSection>
          <InsightSection title="Contradiction lint">
            {insights.contradictions.map((c, i) => (
              <InsightRow
                key={i}
                left={`${c.a} ⚡ ${c.b}`}
                right={c.evidence}
              />
            ))}
          </InsightSection>
        </>
      )}
    </div>
  );
}

function InsightSection({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const empty = Array.isArray(children) ? children.length === 0 : !children;
  return (
    <div>
      <span className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-vellum-dim/90">
        {title}
      </span>
      {empty ? (
        <p className="mt-1 text-[0.72rem] text-vellum-dim">Nothing yet.</p>
      ) : (
        <ul className="mt-0.5">{children}</ul>
      )}
    </div>
  );
}

function InsightRow({
  rank,
  left,
  right,
}: {
  rank?: number;
  left: string;
  right: string;
}) {
  return (
    <li className="flex items-baseline justify-between gap-3 border-b border-vellum-dim/10 py-1 font-mono text-[0.7rem]">
      <span className="flex min-w-0 items-baseline gap-1.5" title={left}>
        {rank != null && <span className="flex-none text-brass">{rank}</span>}
        <span className="truncate">{left}</span>
      </span>
      <span className="flex-none text-vellum-dim">{right}</span>
    </li>
  );
}
