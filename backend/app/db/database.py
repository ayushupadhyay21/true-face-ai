"""PostgreSQL access (psycopg 3 + pgvector). Small connection pool-free helper: the
local research server handles one camera session at a time, so a connection per request
is enough and keeps the dependency list short."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row

from app.core.config import PROJECT_ROOT, Settings
from app.core.errors import AppError, ErrorCode

log = logging.getLogger(__name__)
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"


class Database:
    def __init__(self, conninfo: str):
        self.conninfo = conninfo

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        return cls(settings.database_url)

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        try:
            conn = psycopg.connect(self.conninfo, row_factory=dict_row, connect_timeout=5)
        except psycopg.Error as e:
            log.error("database connection failed: %s", e)
            raise AppError(ErrorCode.DATABASE_ERROR, "Database unavailable") from e
        try:
            register_vector(conn)
            with conn:  # commit on success, rollback on exception
                yield conn
        except psycopg.Error as e:
            log.exception("database error")
            raise AppError(ErrorCode.DATABASE_ERROR, "Database error") from e
        finally:
            conn.close()

    def ping(self) -> dict:
        with self.connect() as c:
            row = c.execute("SELECT version() AS pg, (SELECT extversion FROM pg_extension "
                            "WHERE extname = 'vector') AS pgvector").fetchone()
        return {"postgres": row["pg"].split(",")[0], "pgvector": row["pgvector"]}


def apply_migrations(conninfo: str, directory: Path = MIGRATIONS_DIR) -> list[str]:
    """Apply *.sql files in name order that are not yet recorded in schema_migrations."""
    applied = []
    with psycopg.connect(conninfo, autocommit=False) as conn:
        exists = conn.execute("SELECT to_regclass('schema_migrations') IS NOT NULL").fetchone()[0]
        done = set()
        if exists:
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
        for f in sorted(directory.glob("*.sql")):
            if f.stem in done:
                continue
            conn.execute(f.read_text(encoding="utf-8"))
            conn.execute("INSERT INTO schema_migrations(version) VALUES (%s) ON CONFLICT DO NOTHING", (f.stem,))
            applied.append(f.stem)
        conn.commit()
    return applied
