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


@app.command()
def stop() -> None:
    """Engage the kill switch: write a STOP sentinel that halts in-flight writes."""
    settings = Settings()
    stop_file = settings.db_path.parent / "STOP"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("stop")
    typer.echo(f"Kill switch engaged: {stop_file}")


@app.command()
def review(*, dry_run: bool = True, limit: int | None = None) -> None:
    """Generate reviews for unreviewed books (and post them unless --no-dry-run is set)."""
    from gr_autopilot.orchestrator.pipeline import run_review

    summary = run_review(dry_run=dry_run, limit=limit)
    mode = "dry_run" if summary.dry_run else "live"
    typer.echo(
        f"run={summary.run_id} mode={mode} planned={summary.planned} "
        f"done={summary.done} failed={summary.failed}"
    )


if __name__ == "__main__":
    app()
