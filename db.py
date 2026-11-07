# photo_analysis/db.py
import duckdb

DB_PATH = "photos.duckdb"

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
    error         VARCHAR,
    PRIMARY KEY (path, filename)
);
"""

CREATE_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_photos_full_path ON photos(full_path)",
    "CREATE INDEX IF NOT EXISTS idx_photos_caption ON photos(caption)",
]


def connect(db_path: str = DB_PATH) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(db_path)
    init_db(con)
    return con


def init_db(con: duckdb.DuckDBPyConnection) -> None:
    con.execute(SCHEMA)
    for stmt in CREATE_INDEXES:
        con.execute(stmt)


def upsert_photo(con: duckdb.DuckDBPyConnection, row: dict) -> None:
    con.execute(
        """
        INSERT INTO photos (
            path, filename, full_path, file_size, mtime,
            width, height, exif, caption, caption_model,
            tags, embedding, embed_model, analyzed_at, error
        ) VALUES (
            ?, ?, ?, ?, ?,
            ?, ?, to_json(?::JSON), ?, ?,
            ?, ?, ?, now(), ?
        )
        ON CONFLICT (path, filename) DO UPDATE SET
            file_size     = COALESCE(excluded.file_size, photos.file_size),
            mtime         = COALESCE(excluded.mtime, photos.mtime),
            width         = COALESCE(excluded.width, photos.width),
            height        = COALESCE(excluded.height, photos.height),
            exif          = COALESCE(excluded.exif, photos.exif),
            caption       = COALESCE(excluded.caption, photos.caption),
            caption_model = COALESCE(excluded.caption_model, photos.caption_model),
            tags          = COALESCE(excluded.tags, photos.tags),
            embedding     = COALESCE(excluded.embedding, photos.embedding),
            embed_model   = COALESCE(excluded.embed_model, photos.embed_model),
            analyzed_at   = now(),
            error         = excluded.error
        """,
        [
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
        ],
    )


def pending_photos(
    con: duckdb.DuckDBPyConnection,
    column: str,
    batch_size: int,
) -> list:
    assert column in ("embedding", "caption", "tags")
    return con.execute(
        f"""
        SELECT full_path FROM photos
        WHERE {column} IS NULL AND (error IS NULL OR error = '')
        LIMIT ?
        """,
        [batch_size],
    ).fetchall()