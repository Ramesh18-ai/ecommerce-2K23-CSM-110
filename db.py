import pathlib
import sqlite3

from flask import current_app, g

MIGRATIONS = pathlib.Path(__file__).parent / "migrations"


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite ignores FKs unless this is set per connection
    return conn


def get_db():
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


def migrate(path):
    """Apply every migrations/*.sql file that has not run yet."""
    conn = connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS schema_migrations (name TEXT PRIMARY KEY)")
    done = {r[0] for r in conn.execute("SELECT name FROM schema_migrations")}
    for f in sorted(MIGRATIONS.glob("*.sql")):
        if f.name not in done:
            conn.executescript(f.read_text())
            conn.execute("INSERT INTO schema_migrations (name) VALUES (?)", (f.name,))
            conn.commit()
    conn.close()
