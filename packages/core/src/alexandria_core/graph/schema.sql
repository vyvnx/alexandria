CREATE TABLE IF NOT EXISTS nodes (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL,
  name        TEXT NOT NULL,
  data        TEXT,                 -- JSON
  created_at  TEXT NOT NULL,
  x           REAL,                 -- settled layout position; NULL = unplaced
  y           REAL
);
CREATE TABLE IF NOT EXISTS edges (
  id             INTEGER PRIMARY KEY,
  src_id         INTEGER NOT NULL REFERENCES nodes(id),
  dst_id         INTEGER NOT NULL REFERENCES nodes(id),
  type           TEXT NOT NULL,
  weight         REAL,
  evidence       TEXT,
  from_source_id INTEGER REFERENCES nodes(id),
  created_at     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sources (
  node_id      INTEGER PRIMARY KEY REFERENCES nodes(id),
  url          TEXT,
  author       TEXT,
  published_at TEXT,
  raw_text     TEXT,
  my_note      TEXT,
  summary      TEXT,
  ingested_at  TEXT,
  content_hash TEXT                -- sha256 of the ingested text; dedup gate (A5)
);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON sources(content_hash);
CREATE INDEX IF NOT EXISTS idx_sources_url ON sources(url);
CREATE TABLE IF NOT EXISTS log (
  id     INTEGER PRIMARY KEY,
  ts     TEXT NOT NULL,
  op     TEXT NOT NULL,
  detail TEXT
);
CREATE INDEX IF NOT EXISTS idx_edges_src ON edges(src_id);
CREATE INDEX IF NOT EXISTS idx_edges_dst ON edges(dst_id);
CREATE INDEX IF NOT EXISTS idx_nodes_kind ON nodes(kind);
CREATE INDEX IF NOT EXISTS idx_nodes_name ON nodes(name);
CREATE UNIQUE INDEX IF NOT EXISTS uq_edges ON edges(src_id, dst_id, type);
CREATE TABLE IF NOT EXISTS dismissed (
  id           INTEGER PRIMARY KEY,
  name         TEXT NOT NULL,
  kind         TEXT NOT NULL,
  embedding    BLOB,
  dismissed_at TEXT NOT NULL
);
