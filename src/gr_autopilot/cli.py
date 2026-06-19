import sqlite3
from pathlib import Path

import typer

from gr_autopilot.config import Settings
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.store.db import connect, init_db
from gr_autopilot.store.repository import targets, upsert_books

app = typer.Typer(help="goodreads-autopilot CLI")


def _open_db(settings: Settings) -> sqlite3.Connection:
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    init_db(conn)
    return conn


@app.command()
def ingest(csv_path: Path) -> None:
    """Parse a Goodreads CSV export into the local store."""
    settings = Settings()
    conn = _open_db(settings)
    count = upsert_books(conn, parse_export(csv_path))
    typer.echo(f"Ingested {count} books into {settings.db_path}")


@app.command()
def status() -> None:
    """Show library size and how many books need a review."""
    settings = Settings()
    conn = _open_db(settings)
    total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    n_targets = len(targets(conn, settings.require_rating))
    typer.echo(f"books={total} review_targets={n_targets}")


if __name__ == "__main__":
    app()
