"""Numbered SQL files applied once each, in order, inside the connection's current schema."""

from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg import sql

MIGRATIONS = Path(__file__).resolve().parents[2] / "migrations"


def migrate(url: str, folder: Path = MIGRATIONS) -> list[str]:
    """Apply the files not yet recorded in schema_migrations; returns the versions applied now. Safe to rerun."""
    applied = []
    with psycopg.connect(url, autocommit=True) as conn:
        conn.execute("SELECT pg_advisory_lock(hashtext(current_schema()))")
        try:
            conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version text PRIMARY KEY, "
                         "applied_at timestamptz NOT NULL DEFAULT now())")
            done = {r[0] for r in conn.execute("SELECT version FROM schema_migrations")}
            for path in sorted(folder.glob("[0-9][0-9][0-9]_*.sql")):
                if path.stem in done:
                    continue
                with conn.transaction():
                    conn.execute(path.read_text(encoding="utf-8"))
                    conn.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (path.stem,))
                applied.append(path.stem)
        finally:
            conn.execute("SELECT pg_advisory_unlock(hashtext(current_schema()))")
    return applied


def bootstrap(admin_url: str, app_url: str, readonly_url: str) -> None:
    """Create the two roles and the database named in the app URLs (idempotent; needs the superuser)."""
    app, ro = urlparse(app_url), urlparse(readonly_url)
    dbname = app.path.lstrip("/")
    with psycopg.connect(admin_url, autocommit=True) as conn:
        for user, password in ((app.username, app.password), (ro.username, ro.password)):
            exists = conn.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (user,)).fetchone()
            verb = "ALTER" if exists else "CREATE"
            conn.execute(sql.SQL(verb + " ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(user), sql.Literal(password)))
        if not conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (dbname,)).fetchone():
            conn.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(sql.Identifier(dbname), sql.Identifier(app.username)))
    with psycopg.connect(admin_url.rsplit("/", 1)[0] + "/" + dbname, autocommit=True) as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS citext WITH SCHEMA public")
        conn.execute(sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(sql.Identifier(dbname), sql.Identifier(ro.username)))
        conn.execute(sql.SQL("GRANT ALL ON SCHEMA public TO {}").format(sql.Identifier(app.username)))
