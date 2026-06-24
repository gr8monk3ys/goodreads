import sqlite3
from pathlib import Path

_SCHEMA = Path(__file__).with_name("schema.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Columns added after the first schema release, applied to pre-existing DBs via ALTER.
_BOOKS_ADDED_COLUMNS = {
    "num_pages": "INTEGER",
    "original_pub_year": "INTEGER",
}


def _migrate_books(conn: sqlite3.Connection) -> None:
    """Additively add any missing `books` columns to a legacy DB. Idempotent."""
    existing = {row[1] for row in conn.execute("PRAGMA table_info(books)")}
    for name, decl in _BOOKS_ADDED_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE books ADD COLUMN {name} {decl}")  # noqa: S608 (fixed names)


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    _migrate_books(conn)
    conn.commit()
