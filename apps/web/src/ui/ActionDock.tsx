import { Plus, Search, X, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { api, ApiError } from "../api/client";
import { kindColor } from "../model/graph";
import type { IngestResult, SearchHit } from "../model/types";

/* The action cluster: a minimal floating toolbar bottom-right with two tools —
   the magnifier (search-to-focus) and the star (chart a source). One panel is
   open at a time and rises above the toolbar, which stays reachable while
   inspecting a node. */
type Mode = "none" | "search" | "add";

export function ActionDock({
  onPick,
  onIngested,
}: {
  onPick: (id: number) => void;
  onIngested: (r: IngestResult) => void;
}) {
  const [mode, setMode] = useState<Mode>("none");

  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [active, setActive] = useState(0);

  const [url, setUrl] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const dockRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const urlRef = useRef<HTMLInputElement>(null);

  // Focus the relevant field when a panel opens.
  useEffect(() => {
    if (mode === "search") searchRef.current?.focus();
    if (mode === "add") urlRef.current?.focus();
  }, [mode]);

  // Debounced search — never on every keystroke.
  useEffect(() => {
    const term = q.trim();
    if (!term) {
      setHits([]);
      return;
    }
    const id = setTimeout(async () => {
      try {
        const res = await api.search(term);
        setHits(res.slice(0, 12));
        setActive(0);
      } catch {
        setHits([]);
      }
    }, 180);
    return () => clearTimeout(id);
  }, [q]);

  // Collapse when clicking outside the dock.
  useEffect(() => {
    if (mode === "none") return;
    const onDoc = (e: MouseEvent) => {
      if (dockRef.current && !dockRef.current.contains(e.target as Node)) setMode("none");
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [mode]);

  function pick(hit: SearchHit) {
    onPick(hit.id);
    setQ(hit.name);
    setMode("none");
  }

  function onSearchKey(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      setMode("none");
      return;
    }
    if (!hits.length) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => (a + 1) % hits.length);
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => (a - 1 + hits.length) % hits.length);
    } else if (e.key === "Enter") {
      e.preventDefault();
      pick(hits[active]);
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url.trim() && !note.trim()) {
      setError("Add a link, a note, or both.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const result = await api.ingest({
        url: url.trim() || undefined,
        note: note.trim() || undefined,
      });
      onIngested(result);
      setUrl("");
      setNote("");
      setMode("none");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      ref={dockRef}
      onKeyDown={(e) => e.key === "Escape" && setMode("none")}
      className="absolute right-4 bottom-10 z-50 flex flex-col items-end gap-3"
    >
      {/* Search panel */}
      {mode === "search" && (
        <div className="animate-reveal w-[min(380px,90vw)] origin-bottom-right overflow-hidden rounded-lg border border-line/60 bg-void-2/90 shadow-[0_20px_40px_-30px_#000]">
          <div className="flex items-center gap-2 border-b border-line/60 px-3 py-2.5">
            <Search className="size-4 flex-none text-brass" strokeWidth={1.65} />
            <input
              ref={searchRef}
              type="search"
              aria-label="Search the atlas"
              placeholder="Search the atlas…"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={onSearchKey}
              className="min-w-0 flex-1 bg-transparent text-[0.86rem] text-vellum outline-none placeholder:text-vellum-dim/70"
            />
          </div>
          {hits.length > 0 && (
            <ul role="listbox" className="thin-scrollbar grid max-h-[36vh] gap-1.5 overflow-y-auto p-2">
              {hits.map((h, i) => (
                <li
                  key={h.id}
                  role="option"
                  aria-selected={i === active}
                  onMouseEnter={() => setActive(i)}
                  onMouseDown={(e) => {
                    e.preventDefault();
                    pick(h);
                  }}
                  className="flex cursor-pointer items-center gap-3 rounded-md border border-line/50 bg-transparent px-2.5 py-1.5 text-[0.84rem] leading-tight transition hover:border-brass/50 aria-selected:border-brass/60 aria-selected:bg-brass/12"
                >
                  <span
                    className="grid size-6 flex-none place-items-center rounded-sm bg-void-2/80"
                    style={{ color: kindColor(h.kind) }}
                  >
                    <span
                      className="swatch size-2"
                      style={{ color: kindColor(h.kind), background: kindColor(h.kind) }}
                    />
                  </span>
                  <span className="flex-1 truncate text-[0.82rem] text-vellum">{h.name}</span>
                  <span className="rounded bg-void-2/70 px-1.5 py-0.5 font-mono text-[0.68rem] text-vellum-dim/90">
                    {h.score != null ? h.score.toFixed(2) : h.kind}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Add panel */}
      {mode === "add" && (
        <form
          onSubmit={submit}
          className="panel animate-reveal flex w-[min(330px,82vw)] origin-bottom-right flex-col gap-3 p-4"
        >
          <div className="flex items-start justify-between">
            <div>
              <span className="eyebrow">Chart a source</span>
              <h2 className="font-display mt-0.5 text-[1.35rem] font-medium">Add to the atlas</h2>
            </div>
            <button
              type="button"
              aria-label="Close"
              onClick={() => setMode("none")}
              className="grid size-7 flex-none place-items-center rounded-md border border-line text-vellum-dim transition hover:border-brass hover:text-brass-bright"
            >
              <X className="size-4" />
            </button>
          </div>

          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.72rem] tracking-[0.12em] text-vellum-dim uppercase">Link</span>
            <input
              ref={urlRef}
              className="control"
              type="url"
              inputMode="url"
              placeholder="https://…"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="font-mono text-[0.72rem] tracking-[0.12em] text-vellum-dim uppercase">Your take</span>
            <textarea
              className="control min-h-[3.2rem] resize-y leading-relaxed"
              rows={3}
              placeholder="What you think about it — your perspective becomes part of the graph."
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </label>

          {error && (
            <p className="text-rose text-[0.82rem]" role="alert">
              {error}
            </p>
          )}

          <button type="submit" className="btn btn-primary text-vellum" disabled={busy}>
            {busy ? (
              <>
                <span className="size-3.5 animate-spin rounded-full border-2 border-brass/30 border-t-brass-bright" aria-hidden />
                Reading…
              </>
            ) : (
              "Chart it"
            )}
          </button>
        </form>
      )}

      {/* The compact action toolbar */}
      <div className="flex items-center gap-2 rounded-lg border border-line/60 bg-void-2/80 p-1.5 shadow-[0_18px_40px_-30px_#000] backdrop-blur">
        <DockButton
          icon={Search}
          label="Search"
          ariaLabel="Search the atlas"
          active={mode === "search"}
          shortcut="/"
          onClick={() => setMode(mode === "search" ? "none" : "search")}
        />
        <DockButton
          icon={Plus}
          label="Add"
          ariaLabel="Chart a source"
          active={mode === "add"}
          shortcut="N"
          onClick={() => setMode(mode === "add" ? "none" : "add")}
        />
      </div>
    </div>
  );
}

function DockButton({
  icon: Icon,
  label,
  active,
  ariaLabel,
  shortcut,
  onClick,
}: {
  icon: LucideIcon;
  label: string;
  active: boolean;
  ariaLabel: string;
  shortcut?: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      aria-label={ariaLabel}
      aria-pressed={active}
      onClick={onClick}
      className={`flex items-center gap-2 rounded-md border px-2.5 py-1.5 text-[0.78rem] font-medium transition focus-visible:ring-2 focus-visible:ring-starlight focus-visible:outline-none ${
        active
          ? "border-brass/50 bg-brass/15 text-vellum"
          : "border-transparent text-vellum-dim hover:border-line/60 hover:bg-void-2/90 hover:text-vellum"
      }`}
    >
      <span
        className={`grid size-7 flex-none place-items-center rounded-sm transition ${
          active ? "bg-void-2/70 text-brass-bright" : "bg-transparent text-brass"
        }`}
      >
        <Icon className="size-4" strokeWidth={1.7} />
      </span>
      <span className="truncate text-[0.82rem] leading-none">{label}</span>
      {shortcut && (
        <kbd className="ml-1 hidden rounded border border-line/60 px-1.5 py-0.5 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-vellum-dim sm:inline">
          {shortcut}
        </kbd>
      )}
    </button>
  );
}
