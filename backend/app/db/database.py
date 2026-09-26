"""PostgreSQL access (psycopg 3 + pgvector), backed by a small psycopg_pool ConnectionPool
so live mode's per-tracked-face DB round-trips reuse connections instead of paying full
connect setup on every one."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from pgvector.psycopg import register_vector
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.core.config import PROJECT_ROOT, Settings
from app.core.errors import AppError, ErrorCode

log = logging.getLogger(__name__)
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"


class Database:
    """Small pooled connection helper. Live mode does a DB round-trip per tracked face
    (vector search / auto-enroll), so a pool avoids paying full TCP+TLS+auth setup on every
    one of those instead of just once per pool connection."""

    def __init__(self, conninfo: str):
        self.conninfo = conninfo
        self._pool = ConnectionPool(
            conninfo, min_size=1, max_size=8, kwargs={"row_factory": dict_row}, configure=register_vector,
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> "Database":
        return cls(settings.database_url)

    @contextmanager
    def connect(self) -> Iterator[psycopg.Connection]:
        try:
            with self._pool.connection() as conn:
                yield conn  # pool commits on success, rolls back on exception
        except psycopg.OperationalError as e:
            log.error("database connection failed: %s", e)
            raise AppError(ErrorCode.DATABASE_ERROR, "Database unavailable") from e
        except psycopg.Error as e:
            log.exception("database error")
            raise AppError(ErrorCode.DATABASE_ERROR, "Database error") from e

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
