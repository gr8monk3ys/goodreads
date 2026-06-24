import sqlite3
from pathlib import Path

import typer

from gr_autopilot.config import Settings
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.orchestrator.run import RunSummary
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
def enrich(limit: int | None = None) -> None:
    """Fetch genres for books missing them via public read (no login)."""
    from gr_autopilot.catalog.enrich import enrich_genres
    from gr_autopilot.catalog.goodreads_public import GoodreadsPublicCatalog

    settings = Settings()
    conn = _open_db(settings)
    count = enrich_genres(conn, GoodreadsPublicCatalog(), limit=limit)
    typer.echo(f"enriched {count} books with genres")


@app.command()
def insights(
    *,
    fmt: str = typer.Option("md", "--format", help="md | table | json"),
    enrich: bool = False,
    top: int = 10,
) -> None:
    """Read-only analytics + suggested moves. No account access, no writes."""
    from gr_autopilot.insights.load import load_facts
    from gr_autopilot.insights.metrics import compute
    from gr_autopilot.insights.report import render
    from gr_autopilot.insights.suggestions import suggest

    settings = Settings()
    conn = _open_db(settings)

    if enrich:
        from gr_autopilot.catalog.enrich import enrich_genres
        from gr_autopilot.catalog.goodreads_public import GoodreadsPublicCatalog

        enrich_genres(conn, GoodreadsPublicCatalog())

    facts = load_facts(conn)
    if not facts:
        typer.echo("No library yet — run `gr ingest <goodreads_library_export.csv>` first.")
        return

    metrics = compute(facts)
    typer.echo(render(metrics, suggest(metrics, top=top), fmt=fmt, top=top))


@app.command()
def drafts() -> None:
    """Show review-draft status and the worklist still needing drafts. Never posts."""
    from gr_autopilot.drafts.studio import pending_target_rows, status_counts

    settings = Settings()
    conn = _open_db(settings)
    counts = status_counts(settings.drafts_dir)
    pending = pending_target_rows(conn, settings.drafts_dir, settings.require_rating)

    n_draft, n_approved = counts.get("draft", 0), counts.get("approved", 0)
    typer.echo(
        f"drafts: {n_draft} draft · {n_approved} approved · {len(pending)} pending  "
        f"(dir: {settings.drafts_dir})"
    )
    if pending:
        typer.echo("pending (read + rated, no review yet):")
        for r in pending:
            stars = f"{r['my_rating']}★" if r["my_rating"] else "unrated"
            typer.echo(f"  - [{r['book_id']}] {r['title']} — {r['author']} ({stars})")


@app.command()
def stop() -> None:
    """Engage the kill switch: write a STOP sentinel that halts in-flight writes."""
    settings = Settings()
    stop_file = settings.db_path.parent / "STOP"
    stop_file.parent.mkdir(parents=True, exist_ok=True)
    stop_file.write_text("stop")
    typer.echo(f"Kill switch engaged: {stop_file}")


def _echo_summary(summary: RunSummary) -> None:
    mode = "dry_run" if summary.dry_run else "live"
    typer.echo(
        f"run={summary.run_id} mode={mode} planned={summary.planned} "
        f"done={summary.done} failed={summary.failed}"
    )


@app.command()
def review(*, dry_run: bool = True, limit: int | None = None) -> None:
    """Generate reviews for unreviewed books (and post them unless --no-dry-run is set)."""
    from gr_autopilot.orchestrator.pipeline import run_pipeline

    _echo_summary(run_pipeline(dry_run=dry_run, limit=limit, enrich=False))


@app.command()
def run(*, dry_run: bool = True, limit: int | None = None, enrich: bool = True) -> None:
    """Full pipeline: enrich genres -> build voice index -> generate & post reviews."""
    from gr_autopilot.orchestrator.pipeline import run_pipeline

    _echo_summary(run_pipeline(dry_run=dry_run, limit=limit, enrich=enrich))


if __name__ == "__main__":
    app()
