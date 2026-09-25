"""Create the local research database (and a separate <name>_test database for pytest),
the role and the pgvector extension, then apply migrations.

Needs a PostgreSQL superuser once (normally `postgres`). The admin password is read
from the environment or asked for interactively and is never written anywhere.
The application role and its password come from the project .env
(POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB).

Usage (from the project root):
    .venv\\Scripts\\python.exe scripts/setup_database.py
    # or non-interactive:  $env:PGADMIN_PASSWORD="..."; python scripts/setup_database.py
"""
from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path

import psycopg
from psycopg import sql

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core.config import get_settings  # noqa: E402
from app.db.database import apply_migrations  # noqa: E402


def main() -> None:
    s = get_settings()
    if not s.postgres_password or s.postgres_password == "change_me":
        sys.exit("Set a real POSTGRES_PASSWORD in .env first (copy .env.example to .env).")
    admin_user = os.environ.get("PGADMIN_USER", "postgres")
    admin_pw = os.environ.get("PGADMIN_PASSWORD") or getpass.getpass(f"Password for PostgreSQL admin '{admin_user}': ")
    admin = f"host={s.postgres_host} port={s.postgres_port} user={admin_user} password={admin_pw}"

    with psycopg.connect(admin + " dbname=postgres", autocommit=True) as c:
        if c.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (s.postgres_user,)).fetchone() is None:
            c.execute(sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(s.postgres_user), sql.Literal(s.postgres_password)))
            print(f"created role {s.postgres_user}")
        available = c.execute("SELECT default_version FROM pg_available_extensions WHERE name = 'vector'").fetchone()
        if available is None:
            sys.exit("pgvector is not installed in this PostgreSQL server. Run scripts/install_pgvector.ps1 "
                     "from an elevated PowerShell first (see DATABASE.md).")
        # Main database plus a separate <name>_test database that the test suite may wipe freely.
        for db in (s.postgres_db, f"{s.postgres_db}_test"):
            if c.execute("SELECT 1 FROM pg_database WHERE datname = %s", (db,)).fetchone() is None:
                c.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                    sql.Identifier(db), sql.Identifier(s.postgres_user)))
                print(f"created database {db}")

    for db in (s.postgres_db, f"{s.postgres_db}_test"):
        with psycopg.connect(admin + f" dbname={db}", autocommit=True) as c:
            c.execute("CREATE EXTENSION IF NOT EXISTS vector")
            version = c.execute("SELECT extversion FROM pg_extension WHERE extname='vector'").fetchone()[0]
        applied = apply_migrations(s.model_copy(update={"postgres_db": db}).database_url)
        print(f"{db}: pgvector {version}, migrations applied: {applied or 'none (already up to date)'}")


if __name__ == "__main__":
    main()
