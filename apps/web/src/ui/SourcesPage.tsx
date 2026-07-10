import { useEffect, useState } from "react";

import { api } from "../api/client";
import type { FeedRow, TopicRow } from "../model/types";

/* Sources & topics management (roadmap A3): the curated feed list the worker
   polls, and the topic vocabulary the relevance gate scores against. Plain
   forms + tables in the executions-page visual language. */
export function SourcesPage() {
  const [feeds, setFeeds] = useState<FeedRow[] | null>(null);
  const [topics, setTopics] = useState<TopicRow[] | null>(null);
  const [feedUrl, setFeedUrl] = useState("");
  const [topicName, setTopicName] = useState("");
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      const [f, t] = await Promise.all([api.feeds(), api.topics()]);
      setFeeds(f);
      setTopics(t);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load the registry.");
    }
  }

  useEffect(() => {
    void refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function act(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Request failed.");
    }
  }

  return (
    <div className="app-bg h-full w-full overflow-auto">
      <div className="mx-auto max-w-5xl px-6 py-8">
        <header className="mb-5 flex items-baseline gap-4">
          <h1 className="font-display text-[1.6rem] font-medium">Sources</h1>
          <a
            href="#"
            className="text-[0.82rem] text-vellum-dim hover:text-vellum"
          >
            ← back to the atlas
          </a>
          <a
            href="#/executions"
            className="text-[0.82rem] text-vellum-dim hover:text-vellum"
          >
            executions
          </a>
        </header>

        {error && (
          <p role="alert" className="mb-4 text-rose">
            {error}
          </p>
        )}

        <section className="mb-8">
          <h2 className="mb-2 font-display text-[1.1rem]">Feeds</h2>
          <p className="mb-3 text-[0.82rem] text-vellum-dim">
            Polled on their cadence; new items are relevance-gated by the
            topics below, then charted like any other source.
          </p>
          <form
            className="mb-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!feedUrl.trim()) return;
              void act(() => api.addFeed(feedUrl.trim()));
              setFeedUrl("");
            }}
          >
            <input
              value={feedUrl}
              onChange={(e) => setFeedUrl(e.target.value)}
              placeholder="https://example.com/rss"
              className="panel w-96 px-3 py-1.5 font-mono text-[0.78rem]"
            />
            <button type="submit" className="panel px-3 py-1.5 text-[0.82rem]">
              add feed
            </button>
          </form>
          {feeds && feeds.length === 0 && (
            <p className="text-vellum-dim">No feeds yet — add one above.</p>
          )}
          {feeds && feeds.length > 0 && (
            <table className="w-full border-collapse font-mono text-[0.78rem]">
              <thead>
                <tr className="border-b border-vellum-dim/30 text-left text-vellum-dim">
                  <th className="py-2 pr-4 font-normal">url</th>
                  <th className="py-2 pr-4 font-normal">cadence</th>
                  <th className="py-2 pr-4 font-normal">last polled</th>
                  <th className="py-2 pr-4 font-normal">admitted / filtered</th>
                  <th className="py-2 font-normal" />
                </tr>
              </thead>
              <tbody>
                {feeds.map((f) => (
                  <tr key={f.id} className="border-b border-vellum-dim/10">
                    <td className="max-w-[20rem] truncate py-2 pr-4" title={f.url}>
                      {f.url}
                    </td>
                    <td className="py-2 pr-4">{f.cadence_minutes}m</td>
                    <td className="py-2 pr-4 text-vellum-dim">
                      {f.last_polled_at
                        ? new Date(f.last_polled_at).toLocaleString()
                        : "never"}
                    </td>
                    <td className="py-2 pr-4">
                      {f.items.enqueued} / {f.items.filtered}
                      {f.items.error > 0 && (
                        <span className="text-rose"> · {f.items.error} errors</span>
                      )}
                    </td>
                    <td className="py-2 text-right whitespace-nowrap">
                      <button
                        onClick={() => void act(() => api.pollFeed(f.id))}
                        className="mr-3 text-starlight hover:underline"
                      >
                        poll now
                      </button>
                      <button
                        onClick={() => void act(() => api.removeFeed(f.id))}
                        className="text-rose hover:underline"
                      >
                        remove
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section>
          <h2 className="mb-2 font-display text-[1.1rem]">Topics</h2>
          <p className="mb-3 text-[0.82rem] text-vellum-dim">
            The intake gate's vocabulary. Your strongest graph interests join
            these automatically; no topics means every feed item is admitted.
          </p>
          <form
            className="mb-3 flex gap-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!topicName.trim()) return;
              void act(() => api.addTopic(topicName.trim()));
              setTopicName("");
            }}
          >
            <input
              value={topicName}
              onChange={(e) => setTopicName(e.target.value)}
              placeholder="e.g. spaced repetition"
              className="panel w-96 px-3 py-1.5 font-mono text-[0.78rem]"
            />
            <button type="submit" className="panel px-3 py-1.5 text-[0.82rem]">
              add topic
            </button>
          </form>
          <div className="flex flex-wrap gap-2">
            {topics?.map((t) => (
              <span
                key={t.id}
                className="panel flex items-center gap-2 px-3 py-1 font-mono text-[0.78rem]"
              >
                {t.name}
                <button
                  onClick={() => void act(() => api.removeTopic(t.id))}
                  aria-label={`remove ${t.name}`}
                  className="text-rose hover:underline"
                >
                  ×
                </button>
              </span>
            ))}
            {topics && topics.length === 0 && (
              <span className="text-vellum-dim">
                No topics — the gate is open.
              </span>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
