CREATE TABLE IF NOT EXISTS nodes (
  id          INTEGER PRIMARY KEY,
  kind        TEXT NOT NULL,
  name        TEXT NOT NULL,
  data        TEXT,                 -- JSON
  created_at  TEXT NOT NULL
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
  ingested_at  TEXT
);
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
