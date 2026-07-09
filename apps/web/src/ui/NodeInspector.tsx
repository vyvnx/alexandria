import { ExternalLink, EyeOff, X } from "lucide-react";

import { kindColor } from "../model/graph";
import { isSemantic, type NodeDetail } from "../model/types";

/* The dossier. Slides in from the right on selecting a star: what it is, your
   note (for sources), and every connection with the LLM's evidence for it. */
export function NodeInspector({
  detail,
  loading,
  onClose,
  onPickNeighbor,
  onDismiss,
}: {
  detail: NodeDetail | null;
  loading: boolean;
  onClose: () => void;
  onPickNeighbor: (id: number) => void;
  onDismiss: (id: number) => void;
}) {
  const open = loading || !!detail;
  const node = detail?.node;
  const src = detail?.source;
  const description =
    node && typeof node.data?.description === "string" ? (node.data.description as string) : null;

  return (
    <aside
      aria-hidden={!open}
      aria-label="Node details"
      className={`panel absolute top-0 right-0 bottom-0 z-50 flex w-[min(380px,92vw)] flex-col !rounded-none border-l transition-transform duration-300 ease-out ${
        open ? "translate-x-0" : "translate-x-full"
      }`}
    >
      <header className="border-line/80 flex items-start gap-2 border-b p-4 pb-3">
        <div className="min-w-0 flex-1">
          {node && (
            <span className="flex items-center gap-1.5 font-mono text-[0.72rem] tracking-[0.12em] text-vellum-dim uppercase">
              <span className="swatch" style={{ color: kindColor(node.kind), background: kindColor(node.kind) }} />
              {node.kind}
            </span>
          )}
          <h2 className="font-display mt-1 text-[1.85rem] leading-tight font-medium break-words">
            {node?.name ?? (loading ? "Charting…" : "")}
          </h2>
        </div>
        <button
          type="button"
          aria-label="Close"
          onClick={onClose}
          className="grid size-7 flex-none place-items-center rounded-md border border-line text-vellum-dim transition hover:border-brass hover:text-brass-bright"
        >
          <X className="size-4" />
        </button>
      </header>

      {detail && node && (
        <div className="flex flex-col gap-5 overflow-y-auto p-4">
          {(src?.summary || description) && (
            <section>
              <span className="eyebrow mb-1.5 block">{src ? "Summary" : "About"}</span>
              <p className="text-[0.82rem] leading-relaxed text-vellum/90">{src?.summary || description}</p>
            </section>
          )}

          {src?.my_note && (
            <section>
              <span className="eyebrow mb-1.5 block">My take</span>
              <p className="border-rose border-l-2 pl-2.5 text-[0.82rem] leading-relaxed text-vellum italic">
                {src.my_note}
              </p>
            </section>
          )}

          {src && (src.url || src.author || src.published_at) && (
            <section>
              <span className="eyebrow mb-1.5 block">Source</span>
              <div className="font-mono text-[0.72rem] break-all text-vellum-dim">
                {src.url && (
                  <a
                    href={src.url}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1 text-starlight hover:underline"
                  >
                    <ExternalLink className="size-3 flex-none" />
                    {src.url}
                  </a>
                )}
                {src.author && <div>{src.author}</div>}
                {src.published_at && <div>{src.published_at}</div>}
              </div>
            </section>
          )}

          <section>
            <span className="eyebrow mb-1.5 block">Connections · {detail.neighbors.length}</span>
            {detail.neighbors.length === 0 ? (
              <p className="text-[0.82rem] text-vellum/90">No connections charted yet.</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {detail.neighbors.map((nb, i) => (
                  <li key={`${nb.node.id}-${nb.edge.type}-${i}`}>
                    <button
                      type="button"
                      onClick={() => onPickNeighbor(nb.node.id)}
                      className="bg-void-2/50 border-line/80 grid w-full grid-cols-[auto_1fr] gap-x-2.5 gap-y-0.5 rounded-md border p-2 text-left transition hover:border-brass"
                    >
                      <span
                        className={`col-span-2 font-mono text-[0.72rem] tracking-[0.06em] ${
                          isSemantic(nb.edge.type) ? "text-rose" : "text-brass"
                        }`}
                      >
                        {nb.edge.type}
                        {nb.edge.weight != null ? ` · ${nb.edge.weight.toFixed(2)}` : ""}
                      </span>
                      <span className="swatch self-center" style={{ color: kindColor(nb.node.kind), background: kindColor(nb.node.kind) }} />
                      <span className="font-medium">{nb.node.name}</span>
                      {nb.edge.evidence && (
                        <span className="col-span-2 text-[0.72rem] leading-snug text-vellum-dim">“{nb.edge.evidence}”</span>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {node.kind !== "source" && (
            <section>
              <button
                type="button"
                onClick={() => onDismiss(node.id)}
                className="inline-flex items-center gap-1.5 rounded-md border border-line px-2.5 py-1.5 font-mono text-[0.72rem] tracking-[0.06em] text-vellum-dim transition hover:border-rose hover:text-rose"
              >
                <EyeOff className="size-3.5 flex-none" />
                Not interested
              </button>
              <p className="mt-1.5 text-[0.72rem] leading-snug text-vellum-dim">
                Removes this star and keeps the topic out of future charts.
              </p>
            </section>
          )}
        </div>
      )}
    </aside>
  );
}
