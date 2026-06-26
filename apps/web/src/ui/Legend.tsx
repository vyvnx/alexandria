import { edgeColor, kindColor } from "../model/graph";
import type { FilterMask, GraphCounts } from "../model/filters";
import { NODE_KINDS, SEMANTIC_EDGE, TYPED_EDGES, type EdgeType, type NodeKind } from "../model/types";

/* The legend is the filter — a compact map key pinned near the masthead. Two
   lean sections (Stars = node kinds, Lines = edge types) keep controls tidy in
   a responsive grid; toggling a chip masks that kind / edge-type without
   forcing scroll or stealing focus. */
export function Legend({
  mask,
  counts,
  onToggleKind,
  onToggleEdgeType,
}: {
  mask: FilterMask;
  counts: GraphCounts | null;
  onToggleKind: (k: NodeKind) => void;
  onToggleEdgeType: (t: EdgeType) => void;
}) {
  return (
    <div className="pointer-events-auto absolute right-4 top-[4.75rem] z-30 max-w-[min(520px,92vw)] max-md:hidden">
      <div
        aria-label="Legend and filters"
        className="animate-rise rounded-lg border border-line/60 bg-void-2/80 px-3 py-2.5 shadow-[0_18px_34px_-28px_#000] backdrop-blur"
      >
        <div className="flex items-center gap-2 text-[0.64rem] uppercase tracking-[0.2em] text-vellum-dim/80">
          <span className="font-mono">Legend</span>
          <div className="h-px flex-1 bg-line/60" aria-hidden />
        </div>
        <div className="mt-2.5 flex flex-col gap-2.5">
          <Section title="Stars">
            {NODE_KINDS.map((k) => (
              <Chip key={k} on={mask.kinds[k]} count={counts?.kinds[k]} label={k} onClick={() => onToggleKind(k)}>
                <Swatch color={kindColor(k)} on={mask.kinds[k]} />
              </Chip>
            ))}
          </Section>
          <Section title="Lines">
            {TYPED_EDGES.map((t) => (
              <Chip key={t} on={mask.edgeTypes[t]} count={counts?.edgeTypes[t]} label={t} onClick={() => onToggleEdgeType(t)}>
                <span className="dash" style={{ color: edgeColor(t) }} />
              </Chip>
            ))}
            <Chip
              on={mask.edgeTypes[SEMANTIC_EDGE]}
              count={counts?.edgeTypes[SEMANTIC_EDGE]}
              label="similar-to"
              onClick={() => onToggleEdgeType(SEMANTIC_EDGE)}
            >
              <span className="dash dash-dotted" style={{ color: edgeColor(SEMANTIC_EDGE) }} />
            </Chip>
          </Section>
        </div>
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <span className="font-mono text-[0.62rem] uppercase tracking-[0.18em] text-vellum-dim/90">{title}</span>
      <div className="mt-1.5 grid gap-1.5 sm:grid-cols-2">{children}</div>
    </div>
  );
}

/* Lit when its kind is shown; a hollow ring when filtered out. */
function Swatch({ color, on }: { color: string; on: boolean }) {
  return (
    <span
      className="swatch size-3"
      style={
        on
          ? { color, background: color }
          : { color, background: "transparent", boxShadow: "none", border: `1.5px solid ${color}` }
      }
    />
  );
}

function Chip({
  on,
  count,
  label,
  onClick,
  children,
}: {
  on: boolean;
  count?: number;
  label: string;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`flex w-full items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-left text-[0.76rem] transition focus-visible:ring-2 focus-visible:ring-starlight focus-visible:outline-none ${
        on
          ? "border-brass/40 bg-brass/12 text-vellum"
          : "border-line/50 text-vellum-dim hover:border-brass/35 hover:text-vellum"
      }`}
    >
      <span className="flex min-w-0 items-center gap-1.5 truncate">
        {children}
        <span className="truncate">{label}</span>
      </span>
      {count != null && (
        <span
          className={`flex-none rounded-sm px-1.5 py-0.5 font-mono text-[0.64rem] ${
            on ? "bg-brass/20 text-brass-bright" : "bg-void-2/70 text-vellum-dim"
          }`}
        >
          {count}
        </span>
      )}
    </button>
  );
}
