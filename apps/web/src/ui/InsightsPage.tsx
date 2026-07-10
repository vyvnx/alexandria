import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { AskResult, Digest, Insights } from "../model/types";

/* The intelligence panel (D2–D4): ask the graph a question, see what it
   thinks matters (interests, communities, bridges, undrawn connections,
   trends, contradictions), and pull the weekly digest. Read-only lists in
   the executions-page visual language. */
export function InsightsPage() {
  const [insights, setInsights] = useState<Insights | null>(null);
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<AskResult | null>(null);
  const [digest, setDigest] = useState<Digest | null>(null);
  const [error, setError] = useState<string | null>(null);

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

  async function loadDigest(narrative: boolean) {
    try {
      setDigest(await api.digest(narrative));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't build the digest.");
    }
  }

  return (
    <div className="app-bg h-full w-full overflow-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-5 flex items-baseline gap-4">
          <h1 className="font-display text-[1.6rem] font-medium">Insights</h1>
          <a href="#" className="text-[0.82rem] text-vellum-dim hover:text-vellum">
            ← back to the atlas
          </a>
        </header>

        {error && (
          <p role="alert" className="mb-4 text-rose">
            {error}
          </p>
        )}

        <section className="mb-8">
          <h2 className="mb-2 font-display text-[1.1rem]">Ask the graph</h2>
          <form className="flex gap-2" onSubmit={submitAsk}>
            <input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="what connects X to Y?"
              className="panel w-[28rem] px-3 py-1.5 font-mono text-[0.78rem]"
            />
            <button type="submit" className="panel px-3 py-1.5 text-[0.82rem]">
              {asking ? "consulting…" : "ask"}
            </button>
          </form>
          {answer && (
            <div className="panel mt-3 max-w-3xl px-4 py-3 text-[0.88rem]">
              <p>{answer.answer}</p>
              {answer.citations.length > 0 && (
                <p className="mt-2 font-mono text-[0.72rem] text-vellum-dim">
                  {answer.citations.map((c) => `[${c.n}] ${c.name}`).join(" · ")}
                </p>
              )}
            </div>
          )}
        </section>

        {insights && (
          <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
            <Section title="Strongest interests">
              {insights.strongest_interests.map((n) => (
                <Row key={n.id} left={n.name} right={n.score.toFixed(4)} />
              ))}
            </Section>
            <Section title="Emergent communities">
              {insights.communities.map((c) => (
                <Row key={c.id} left={c.label} right={`${c.size} nodes`} />
              ))}
            </Section>
            <Section title="Serendipity bridges">
              {insights.bridges.map((n) => (
                <Row key={n.id} left={n.name} right={n.score.toFixed(2)} />
              ))}
            </Section>
            <Section title="Connections you haven't drawn">
              {insights.suggested_connections.map((s, i) => (
                <Row
                  key={i}
                  left={`${s.a.name} ↔ ${s.b.name}`}
                  right={`${s.common} shared`}
                />
              ))}
            </Section>
            <Section title="Circling lately">
              {insights.trending.map((t) => (
                <Row key={t.name} left={t.name} right={t.weight.toFixed(2)} />
              ))}
            </Section>
            <Section title="Contradiction lint">
              {insights.contradictions.map((c, i) => (
                <Row key={i} left={`${c.a} ⚡ ${c.b}`} right={c.evidence} />
              ))}
            </Section>
          </div>
        )}

        <section className="mt-10">
          <h2 className="mb-2 font-display text-[1.1rem]">Digest</h2>
          <div className="mb-3 flex gap-2">
            <button
              onClick={() => void loadDigest(false)}
              className="panel px-3 py-1.5 text-[0.82rem]"
            >
              what did the graph learn this week?
            </button>
            {digest && !digest.narrative && (
              <button
                onClick={() => void loadDigest(true)}
                className="panel px-3 py-1.5 text-[0.82rem]"
              >
                narrate it (one llm call)
              </button>
            )}
          </div>
          {digest && (
            <div className="panel max-w-3xl px-4 py-3 text-[0.88rem]">
              <p className="font-mono text-[0.78rem] text-vellum-dim">
                {digest.new_sources} sources · {digest.new_nodes} nodes in{" "}
                {digest.days} days · {digest.contradictions} contradiction(s)
              </p>
              {digest.narrative && <p className="mt-2">{digest.narrative}</p>}
              {digest.top_new.length > 0 && (
                <p className="mt-2">
                  New & notable: {digest.top_new.map((n) => n.name).join(", ")}
                </p>
              )}
              {digest.resurface.length > 0 && (
                <p className="mt-2">
                  Worth revisiting:{" "}
                  {digest.resurface.map((n) => n.name).join(", ")}
                </p>
              )}
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  const empty = Array.isArray(children) ? children.length === 0 : !children;
  return (
    <section>
      <h2 className="mb-2 font-display text-[1.1rem]">{title}</h2>
      {empty ? (
        <p className="text-[0.82rem] text-vellum-dim">Nothing yet.</p>
      ) : (
        <ul className="space-y-1">{children}</ul>
      )}
    </section>
  );
}

function Row({ left, right }: { left: string; right: string }) {
  return (
    <li className="flex items-baseline justify-between gap-4 border-b border-vellum-dim/10 py-1 font-mono text-[0.78rem]">
      <span className="truncate" title={left}>
        {left}
      </span>
      <span className="flex-none text-vellum-dim">{right}</span>
    </li>
  );
}
