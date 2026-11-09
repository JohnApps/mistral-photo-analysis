# common.py
# check for existing entries
# no location etc.
import time
import warnings

import duckdb
from PIL import Image

warnings.filterwarnings("ignore", message="Image size")
Image.MAX_IMAGE_PIXELS = None

DB_PATH = "photos.duckdb"
COMMIT_EVERY = 500  # rows per transaction, per DuckDB guidance

# No PRIMARY KEY and no indexes: DuckDB is an OLAP engine; uniqueness of
# full_path is enforced by scan.py (application-level dedup), and the
# analysis scripts only UPDATE rows they selected from the table itself.
SCHEMA = """
CREATE TABLE IF NOT EXISTS photos (
    path          VARCHAR NOT NULL,
    filename      VARCHAR NOT NULL,
    full_path     VARCHAR NOT NULL,
    file_size     BIGINT,
    mtime         TIMESTAMP,
    width         INTEGER,
    height        INTEGER,
    exif          JSON,
    caption       VARCHAR,
    caption_model VARCHAR,
    tags          VARCHAR[],
    embedding     FLOAT[512],
    embed_model   VARCHAR,
    analyzed_at   TIMESTAMP,
    error         VARCHAR
);
"""

INSERT_SQL = """
INSERT INTO photos (
    path, filename, full_path, file_size, mtime,
    width, height, exif, caption, caption_model,
    tags, embedding, embed_model, analyzed_at, error
) VALUES (
    ?, ?, ?, ?, ?,
    ?, ?, to_json(?::JSON), ?, ?,
    ?, ?, ?, now(), ?
)
"""

UPDATE_EMBED_SQL = """
UPDATE photos SET embedding = ?, embed_model = ?, analyzed_at = now()
WHERE full_path = ?
"""

UPDATE_TAGS_SQL = """
UPDATE photos SET tags = ?, embed_model = ?, analyzed_at = now()
WHERE full_path = ?
"""

UPDATE_CAPTION_SQL = """
UPDATE photos SET caption = ?, caption_model = ?, analyzed_at = now()
WHERE full_path = ?
"""

UPDATE_ERROR_SQL = """
UPDATE photos SET error = ?, analyzed_at = now()
WHERE full_path = ?
"""


def _insert_params(row: dict) -> list:
    return [
        row.get("path"),
        row.get("filename"),
        row.get("full_path"),
        row.get("file_size"),
        row.get("mtime"),
        row.get("width"),
        row.get("height"),
        row.get("exif_json"),
        row.get("caption"),
        row.get("caption_model"),
        row.get("tags"),
        row.get("embedding"),
        row.get("embed_model"),
        row.get("error"),
    ]


def connect(db_path: str = DB_PATH):
    con = duckdb.connect(db_path)
    con.execute("SET preserve_insertion_order = false")
    con.execute(SCHEMA)
    return con


def existing_paths(con) -> set:
    """All full_paths currently in the table (for scan dedup)."""
    return {r[0] for r in con.execute("SELECT full_path FROM photos").fetchall()}


class Inserter:
    """Buffered plain INSERTs: one transaction per COMMIT_EVERY rows."""

    def __init__(self, con):
        self.con = con
        self.buf = []

    def add(self, row: dict) -> None:
        self.buf.append(_insert_params(row))
        if len(self.buf) >= COMMIT_EVERY:
            self.flush()

    def flush(self) -> None:
        if self.buf:
            self.con.executemany(INSERT_SQL, self.buf)
            self.con.commit()
            self.buf = []


class Updater:
    """Buffered UPDATEs by full_path: one transaction per COMMIT_EVERY rows."""

    def __init__(self, con, sql):
        self.con = con
        self.sql = sql
        self.buf = []

    def add(self, params: list) -> None:
        self.buf.append(params)
        if len(self.buf) >= COMMIT_EVERY:
            self.flush()

    def flush(self) -> None:
        if self.buf:
            self.con.executemany(self.sql, self.buf)
            self.con.commit()
            self.buf = []


def pending_photos(con, column: str, batch_size: int) -> list:
    assert column in ("embedding", "caption", "tags")
    return con.execute(
        f"""
        SELECT full_path FROM photos
        WHERE {column} IS NULL AND (error IS NULL OR error = '')
        LIMIT ?
        """,
        [batch_size],
    ).fetchall()


def split_path(full_path: str):
    norm = full_path.replace("\\", "/")
    path, _, filename = norm.rpartition("/")
    return path or ".", filename


def status(con) -> None:
    row = con.execute(
        """
        SELECT
            count(*),
            count(embedding),
            count(tags),
            count(caption),
            count(*) FILTER (WHERE error IS NOT NULL AND error <> '')
        FROM photos
        """
    ).fetchone()
    print(
        f"total={row[0]} embedded={row[1]} tagged={row[2]} "
        f"captioned={row[3]} errors={row[4]}"
    )