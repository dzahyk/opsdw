from __future__ import annotations

import psycopg
from psycopg import sql

from .config import SQL_DIR, conninfo


def connect(dbname: str | None = None, autocommit: bool = False) -> psycopg.Connection:
    return psycopg.connect(conninfo(dbname), autocommit=autocommit)


def ensure_database(dbname: str, drop: bool = False) -> None:
    """Create (optionally recreate) a database on the same server."""
    with connect("postgres", autocommit=True) as conn:
        if drop:
            conn.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(dbname)))
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone()
        if not exists:
            conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(dbname)))


def apply_ddl(conn: psycopg.Connection) -> list[str]:
    """Apply every sql/ddl/*.sql file in order. All DDL is idempotent."""
    applied = []
    for path in sorted((SQL_DIR / "ddl").glob("*.sql")):
        conn.execute(path.read_text())
        applied.append(path.name)
    for path in sorted((SQL_DIR / "semantic").glob("*.sql")):
        conn.execute(path.read_text())
        applied.append(f"semantic/{path.name}")
    conn.commit()
    return applied
