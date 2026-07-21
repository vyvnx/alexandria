import json
import sqlite3
import struct
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from .models import Node, Edge, KIND_SOURCE, SYMMETRIC_EDGES

try:
    import sqlite_vec
except ImportError:  # pragma: no cover
    sqlite_vec = None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class GraphStore:
    def __init__(self, db_path: str):
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        # check_same_thread=False: FastAPI runs sync endpoints in a worker thread.
        # This is a single-user local app, so access is effectively serialized.
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.vec_available = self._load_vec()

    def _load_vec(self) -> bool:
        if sqlite_vec is None or not hasattr(self.conn, "enable_load_extension"):
            return False
        try:
            self.conn.enable_load_extension(True)
            sqlite_vec.load(self.conn)
            self.conn.enable_load_extension(False)
            return True
        except (AttributeError, sqlite3.OperationalError):  # pragma: no cover
            return False

    def init_schema(self) -> None:
        # lazy migration: dbs created before the dedup column need it added
        # before schema.sql's index on it can be created
        cols = [r[1] for r in self.conn.execute("PRAGMA table_info(sources)")]
        if cols and "content_hash" not in cols:
            self.conn.execute("ALTER TABLE sources ADD COLUMN content_hash TEXT")
        # lazy migration: settled layout positions (server-side positions spec)
        node_cols = [r[1] for r in self.conn.execute("PRAGMA table_info(nodes)")]
        if node_cols and "x" not in node_cols:
            self.conn.execute("ALTER TABLE nodes ADD COLUMN x REAL")
            self.conn.execute("ALTER TABLE nodes ADD COLUMN y REAL")
        sql = (resources.files("alexandria_core.graph") / "schema.sql").read_text()
        self.conn.executescript(sql)
        if self.vec_available:
            self.conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS vec_nodes USING vec0("
                "node_id INTEGER PRIMARY KEY, embedding FLOAT[1024] distance_metric=cosine)"
            )
        self.conn.commit()

    # ---- nodes ----
    def add_node(self, kind: str, name: str, data: dict | None = None) -> int:
        cur = self.conn.execute(
            "INSERT INTO nodes(kind, name, data, created_at) VALUES (?,?,?,?)",
            (kind, name, json.dumps(data or {}), _now()),
        )
        self.conn.commit()
        return cur.lastrowid

    def _row_to_node(self, r: sqlite3.Row) -> Node:
        return Node(id=r["id"], kind=r["kind"], name=r["name"],
                    data=json.loads(r["data"] or "{}"), created_at=r["created_at"],
                    x=r["x"], y=r["y"])

    def set_positions(self, positions: dict[int, tuple[float, float]]) -> int:
        """Bulk-write settled layout positions, rounded to 2 decimals (keeps the
        graph wire light). Unknown ids are ignored — a node can be dismissed
        between the client's layout settling and the save arriving."""
        cur = self.conn.executemany(
            "UPDATE nodes SET x=?, y=? WHERE id=?",
            [(round(x, 2), round(y, 2), nid) for nid, (x, y) in positions.items()],
        )
        self.conn.commit()
        return cur.rowcount

    def get_node(self, node_id: int) -> Node | None:
        r = self.conn.execute("SELECT * FROM nodes WHERE id=?", (node_id,)).fetchone()
        return self._row_to_node(r) if r else None

    def find_node_by_name(self, name: str, kind: str) -> Node | None:
        r = self.conn.execute(
            "SELECT * FROM nodes WHERE name=? AND kind=? ORDER BY id LIMIT 1", (name, kind)
        ).fetchone()
        return self._row_to_node(r) if r else None

    def all_nodes(self) -> list[Node]:
        return [self._row_to_node(r) for r in self.conn.execute("SELECT * FROM nodes")]

    # ---- sources ----
    def add_source(self, node_id: int, *, url, author, published_at,
                   raw_text, my_note, summary, content_hash=None) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO sources"
            "(node_id,url,author,published_at,raw_text,my_note,summary,ingested_at,"
            "content_hash) VALUES (?,?,?,?,?,?,?,?,?)",
            (node_id, url, author, published_at, raw_text, my_note, summary, _now(),
             content_hash),
        )
        self.conn.commit()

    def get_source(self, node_id: int) -> dict | None:
        r = self.conn.execute("SELECT * FROM sources WHERE node_id=?", (node_id,)).fetchone()
        return dict(r) if r else None

    def find_source_by_url(self, url: str) -> int | None:
        r = self.conn.execute("SELECT node_id FROM sources WHERE url=? LIMIT 1",
                              (url,)).fetchone()
        return r["node_id"] if r else None

    def find_source_by_hash(self, content_hash: str) -> int | None:
        r = self.conn.execute("SELECT node_id FROM sources WHERE content_hash=? LIMIT 1",
                              (content_hash,)).fetchone()
        return r["node_id"] if r else None

    # ---- edges ----
    def add_edge(self, src_id: int, dst_id: int, type: str, *,
                 weight=None, evidence=None, from_source_id=None) -> int | None:
        if type in SYMMETRIC_EDGES and src_id > dst_id:
            src_id, dst_id = dst_id, src_id
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO edges"
            "(src_id,dst_id,type,weight,evidence,from_source_id,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (src_id, dst_id, type, weight, evidence, from_source_id, _now()),
        )
        self.conn.commit()
        return cur.lastrowid if cur.rowcount else None

    def _row_to_edge(self, r: sqlite3.Row) -> Edge:
        return Edge(id=r["id"], src_id=r["src_id"], dst_id=r["dst_id"], type=r["type"],
                    weight=r["weight"], evidence=r["evidence"],
                    from_source_id=r["from_source_id"], created_at=r["created_at"])

    def all_edges(self) -> list[Edge]:
        return [self._row_to_edge(r) for r in self.conn.execute("SELECT * FROM edges")]

    def edges_for(self, node_id: int) -> list[Edge]:
        rows = self.conn.execute(
            "SELECT * FROM edges WHERE src_id=? OR dst_id=?", (node_id, node_id))
        return [self._row_to_edge(r) for r in rows]

    def reach(self, start_id: int, k: int) -> list[int]:
        rows = self.conn.execute(
            """
            WITH RECURSIVE reach(id, depth) AS (
              SELECT ?, 0
              UNION
              SELECT CASE WHEN e.src_id = r.id THEN e.dst_id ELSE e.src_id END, depth + 1
              FROM edges e JOIN reach r ON e.src_id = r.id OR e.dst_id = r.id
              WHERE depth < ?
            ) SELECT DISTINCT id FROM reach
            """, (start_id, k)).fetchall()
        return [r[0] for r in rows]

    # ---- vectors ----
    def add_embedding(self, node_id: int, vector: list[float]) -> None:
        if not self.vec_available:
            return
        blob = struct.pack(f"{len(vector)}f", *vector)
        self.conn.execute(
            "INSERT OR REPLACE INTO vec_nodes(node_id, embedding) VALUES (?, ?)",
            (node_id, blob),
        )
        self.conn.commit()

    def get_embedding(self, node_id: int) -> list[float] | None:
        if not self.vec_available:
            return None
        r = self.conn.execute(
            "SELECT embedding FROM vec_nodes WHERE node_id=?", (node_id,)).fetchone()
        if r is None:
            return None
        blob = r["embedding"]
        return list(struct.unpack(f"{len(blob) // 4}f", blob))

    def knn(self, vector: list[float], k: int) -> list[tuple[int, float]]:
        if not self.vec_available:
            return []
        blob = struct.pack(f"{len(vector)}f", *vector)
        rows = self.conn.execute(
            "SELECT node_id, distance FROM vec_nodes "
            "WHERE embedding MATCH ? AND k = ? ORDER BY distance",
            (blob, k),
        ).fetchall()
        return [(r["node_id"], 1.0 - r["distance"]) for r in rows]  # cosine distance → score

    def interest_pool(self, *, half_life_days: float, min_weight: float,
                      ) -> list[tuple[str, float, list[float] | None]]:
        """Behaviorally-confirmed interests: entity/concept nodes referenced by
        mentions/about edges from distinct sources, each source's contribution
        exponentially decayed by ingest age. Returns (name, weight, embedding)
        sorted by weight descending, only nodes with weight >= min_weight."""
        now = datetime.now(timezone.utc)
        rows = self.conn.execute(
            "SELECT e.dst_id AS node_id, s.ingested_at AS ingested_at "
            "FROM edges e JOIN sources s ON s.node_id = e.src_id "
            "WHERE e.type IN ('mentions','about') "
            "GROUP BY e.dst_id, e.src_id",  # one vote per (source, node) pair
        ).fetchall()
        weights: dict[int, float] = {}
        for r in rows:
            age_days = (now - datetime.fromisoformat(r["ingested_at"])).total_seconds() / 86400
            weights[r["node_id"]] = weights.get(r["node_id"], 0.0) + 0.5 ** (age_days / half_life_days)
        out = []
        for node_id, w in weights.items():
            if w < min_weight:
                continue
            node = self.get_node(node_id)
            if node is not None:
                out.append((node.name, w, self.get_embedding(node_id)))
        out.sort(key=lambda t: t[1], reverse=True)
        return out

    # ---- dismissed (the "not interested" feedback loop) ----
    def dismiss_node(self, node_id: int) -> str:
        """Delete a node and remember it so future ingests suppress the topic.
        Returns the dismissed name. Raises ValueError for missing or source nodes."""
        node = self.get_node(node_id)
        if node is None:
            raise ValueError(f"node {node_id} not found")
        if node.kind == KIND_SOURCE:
            raise ValueError("source nodes cannot be dismissed")
        vec = self.get_embedding(node_id)
        blob = struct.pack(f"{len(vec)}f", *vec) if vec is not None else None
        self.conn.execute(
            "INSERT INTO dismissed(name, kind, embedding, dismissed_at) VALUES (?,?,?,?)",
            (node.name, node.kind, blob, _now()),
        )
        self.conn.execute("DELETE FROM edges WHERE src_id=? OR dst_id=?", (node_id, node_id))
        if self.vec_available:
            self.conn.execute("DELETE FROM vec_nodes WHERE node_id=?", (node_id,))
        self.conn.execute("DELETE FROM nodes WHERE id=?", (node_id,))
        self.conn.commit()
        self.log("dismiss", f"node={node_id} {node.name!r}")
        return node.name

    def all_dismissed(self) -> list[tuple[str, list[float] | None]]:
        """(name, embedding) for every dismissed record; embedding may be None."""
        out: list[tuple[str, list[float] | None]] = []
        for r in self.conn.execute("SELECT name, embedding FROM dismissed"):
            blob = r["embedding"]
            vec = list(struct.unpack(f"{len(blob) // 4}f", blob)) if blob else None
            out.append((r["name"], vec))
        return out

    # ---- log ----
    def log(self, op: str, detail: str) -> None:
        self.conn.execute("INSERT INTO log(ts, op, detail) VALUES (?,?,?)", (_now(), op, detail))
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
