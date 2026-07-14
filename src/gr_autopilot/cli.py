from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from gr_autopilot.config import Settings
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.orchestrator.run import RunSummary
from gr_autopilot.store.db import connect, init_db
from gr_autopilot.store.repository import targets, upsert_books

if TYPE_CHECKING:
    from gr_autopilot.actions.core import ActionResult
    from gr_autopilot.actions.executor import ActionExecutor
    from gr_autopilot.actions.plan import PlanItem

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
def plan(*, top: int = 5) -> None:
    """One consolidated path to a stronger profile: priorities, read-next, gaps, signature."""
    from gr_autopilot.curate import hygiene, tbr_triage
    from gr_autopilot.drafts.studio import status_counts
    from gr_autopilot.insights.load import load_facts
    from gr_autopilot.insights.metrics import compute
    from gr_autopilot.insights.suggestions import suggest
    from gr_autopilot.presence import signature

    settings = Settings()
    conn = _open_db(settings)
    facts = load_facts(conn)
    if not facts:
        typer.echo("No library yet — run `gr ingest <goodreads_library_export.csv>` first.")
        return

    metrics = compute(facts)
    typer.echo("# 🎯 Path to a stronger Goodreads profile\n")

    typer.echo("## Do these, highest impact first")
    for s in suggest(metrics, top=top):
        typer.echo(f"  [{s.impact:>6}] {s.title}")

    typer.echo("\n## Read next (you loved these authors)")
    for t in tbr_triage(facts, top=top):
        typer.echo(f"  - {t.book.title} — {t.book.author}  ({t.reason})")

    h = hygiene(facts)
    counts = status_counts(settings.drafts_dir)
    typer.echo(
        f"\n## Quick wins: rate {len(h.unrated_reads)} · date {len(h.undated_reads)} · "
        f"Drafts {counts.get('draft', 0)} to edit, {counts.get('approved', 0)} approved"
    )

    sig = signature(facts)
    if sig.five_star_titles:
        typer.echo("\n## Your signature: " + ", ".join(sig.five_star_titles[:top]))

    typer.echo("\nDetail: gr insights · gr curate · gr presence · gr drafts")


@app.command()
def curate(*, top: int = 20) -> None:
    """Concrete curation plan: TBR triage, shelf taxonomy, hygiene worklists. Read-only."""
    from gr_autopilot.curate import hygiene, shelf_plan, tbr_triage
    from gr_autopilot.insights.load import load_facts

    settings = Settings()
    conn = _open_db(settings)
    facts = load_facts(conn)
    if not facts:
        typer.echo("No library yet — run `gr ingest <goodreads_library_export.csv>` first.")
        return

    h = hygiene(facts)
    triaged = tbr_triage(facts, top=top)
    shelves = shelf_plan(facts)

    typer.echo("# 🧹 Curation plan\n")
    typer.echo(f"## Read next — to-read ranked by author affinity (top {top})")
    for t in triaged:
        typer.echo(f"  - {t.book.title} — {t.book.author}  ({t.reason})")

    typer.echo("\n## Proposed shelves (custom shelves to create)")
    for s in shelves:
        typer.echo(f"  - {s.name} [{s.kind}] — {s.book_count} books")

    typer.echo("\n## Data hygiene")
    typer.echo(f"  {len(h.unrated_reads)} unrated reads · {len(h.undated_reads)} undated reads")
    for b in h.unrated_reads[:top]:
        typer.echo(f"  - rate: {b.title} — {b.author}")
    for b in h.undated_reads[:top]:
        typer.echo(f"  - date: {b.title} — {b.author}")


_DASHBOARD_BIO = (
    "Mostly philosophy that snuck into novels — Dostoevsky, Hesse, Camus, Kafka, Frankl — "
    "though my shelf gives me away as less serious than that sounds (there's Percy Jackson "
    "on here too). I read slowly, rate honestly, and only bother reviewing the ones that "
    "actually stuck with me. Always up for a recommendation that argues with something I "
    "already love."
)


@app.command()
def dashboard(*, out: Path = Path("data/dashboard.html")) -> None:
    """Generate a self-contained HTML action board of your target profile state. Read-only."""
    from gr_autopilot.actions.plan import is_unfilled, parse_plan
    from gr_autopilot.dashboard import build_dashboard_html
    from gr_autopilot.drafts.studio import has_draft, status_counts
    from gr_autopilot.insights.load import load_facts

    settings = Settings()
    conn = _open_db(settings)
    facts = load_facts(conn)
    if not facts:
        typer.echo("No library yet — run `gr ingest <goodreads_library_export.csv>` first.")
        return

    # pull proposed ratings from an existing write-plan.csv, if present
    proposed: dict[int, int] = {}
    plan_path = settings.db_path.parent / "write-plan.csv"
    if plan_path.exists():
        for item in parse_plan(plan_path.read_text(encoding="utf-8")):
            if item.action == "set_rating" and item.book_id and not is_unfilled(item):
                proposed[item.book_id] = int(item.value)

    drafted = {f.book_id for f in facts if has_draft(settings.drafts_dir, f.book_id)}
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        build_dashboard_html(
            facts,
            draft_counts=status_counts(settings.drafts_dir),
            proposed_ratings=proposed,
            drafted_ids=drafted,
            bio=_DASHBOARD_BIO,
        ),
        encoding="utf-8",
    )
    typer.echo(f"wrote {out} — open it in a browser; ticks persist locally.")


@app.command()
def launch(*, out: Path = Path("data/launch-plan.md"), per_week: int = 3) -> None:
    """Sequence the action board into a paced launch campaign (what to do first). Read-only."""
    from gr_autopilot.drafts.studio import has_draft
    from gr_autopilot.insights.load import load_facts
    from gr_autopilot.launch import build_launch_plan, render_markdown

    settings = Settings()
    conn = _open_db(settings)
    facts = load_facts(conn)
    if not facts:
        typer.echo("No library yet — run `gr ingest <goodreads_library_export.csv>` first.")
        return

    drafted = {f.book_id for f in facts if has_draft(settings.drafts_dir, f.book_id)}
    plan = build_launch_plan(
        facts, drafted_ids=drafted, bio=_DASHBOARD_BIO, reviews_per_week=per_week
    )
    md = render_markdown(plan)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    typer.echo(md)
    typer.echo(f"\nwrote {out} · full board: gr dashboard")


@app.command()
def backup(*, dest: Path | None = None) -> None:
    """Tar data/ + drafts/ to a timestamped archive outside the repo.

    These are the only irreplaceable artifacts (git-ignored by design), so they
    are the one thing git can't restore. Run this after any drafting session.
    """
    from datetime import datetime

    from gr_autopilot.backup import backup_artifacts

    settings = Settings()
    sources = [settings.db_path.parent, settings.drafts_dir.parent]
    try:
        archive = backup_artifacts(sources, dest or settings.backup_dir, timestamp=datetime.now())
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc
    size_kb = archive.stat().st_size / 1024
    typer.echo(f"backed up {', '.join(str(s) for s in sources if s.exists())}")
    typer.echo(f"-> {archive} ({size_kb:.0f} KB)")


@app.command()
def presence(*, top: int = 5) -> None:
    """Profile-presence pack: your reading signature + best reviews to feature. Read-only."""
    from gr_autopilot.insights.load import load_facts
    from gr_autopilot.presence import best_reviews, signature

    settings = Settings()
    conn = _open_db(settings)
    facts = load_facts(conn)
    if not facts:
        typer.echo("No library yet — run `gr ingest <goodreads_library_export.csv>` first.")
        return

    sig = signature(facts)
    typer.echo("# ✨ Profile presence pack\n")
    typer.echo("## Your reading signature")
    if sig.five_star_titles:
        typer.echo("- 5★ canon: " + ", ".join(sig.five_star_titles))
    if sig.top_authors:
        authors = ", ".join(f"{a} ({n})" for a, n in sig.top_authors[:top])
        typer.echo("- Signature authors: " + authors)
    if sig.top_eras:
        typer.echo("- Eras you live in: " + ", ".join(f"{b} ({n})" for b, n in sig.top_eras[:top]))
    if sig.top_genres:
        typer.echo("- Genres: " + ", ".join(f"{g} ({n})" for g, n in sig.top_genres[:top]))

    typer.echo("\n## Best reviews to feature")
    for r in best_reviews(facts, top=top):
        typer.echo(f"- {r.title} — {r.author} ({r.my_rating}★, {r.word_count} words)")
        typer.echo(f'    "{r.snippet}"')


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


def _dispatch_write(executor: ActionExecutor, item: PlanItem) -> ActionResult:
    if item.action == "ensure_shelf":
        return executor.ensure_shelf(item.value)
    if item.book_id is None:
        raise ValueError(f"{item.action} requires a book_id")
    if item.action == "set_rating":
        return executor.set_rating(item.book_id, int(item.value))
    if item.action == "set_date":
        return executor.set_date(item.book_id, item.value)
    if item.action == "add_to_list":
        return executor.add_to_list(item.value, item.book_id)
    return executor.set_shelf(item.book_id, item.value)


@app.command()
def apply(plan_csv: Path, *, dry_run: bool = True) -> None:
    """Apply a write-plan CSV (ratings/dates/shelves/list-adds) to your account. DRY-RUN by default.

    Reviews and social actions are never applyable here. Live writes (--no-dry-run) need the
    browser extra and a prior `gr login`, and carry account-suspension risk.
    """
    from collections import Counter

    from gr_autopilot.actions.core import NullBackend, Throttle
    from gr_autopilot.actions.executor import ActionExecutor
    from gr_autopilot.actions.plan import is_unfilled, parse_plan
    from gr_autopilot.store.repository import finish_run, start_run

    settings = Settings()
    conn = _open_db(settings)
    all_items = parse_plan(plan_csv.read_text(encoding="utf-8"))
    ready = [it for it in all_items if not is_unfilled(it)]
    unfilled = len(all_items) - len(ready)
    capped = max(0, len(ready) - settings.max_actions_per_run)  # blast-radius cap per run
    items = ready[: settings.max_actions_per_run]
    stop_file = settings.db_path.parent / "STOP"
    run_id = start_run(conn, "dry_run" if dry_run else "live")

    if dry_run:
        ex = ActionExecutor(
            conn,
            NullBackend(),
            run_id=run_id,
            settings=settings,
            throttle=Throttle(sleeper=lambda _: None),
            dry_run=True,
            stop_file=stop_file,
        )
        tally: Counter[str] = Counter(_dispatch_write(ex, it).status for it in items)
        finish_run(conn, run_id, len(items), 0, tally.get("failed", 0))
        would = tally.get("dry_run", 0)
        already = tally.get("skipped_idempotent", 0)
        typer.echo(
            f"apply (DRY RUN — no writes made): {len(items)} planned · "
            f"{would} would-write · {already} already-done · {unfilled} unfilled (skipped) · "
            f"{capped} capped (raise GR_MAX_ACTIONS_PER_RUN)"
        )
        typer.echo("Review the plan, then `gr login` + re-run with --no-dry-run to write.")
        return

    from gr_autopilot.actions.graphql_backend import GoodreadsGraphQLBackend
    from gr_autopilot.browser.session import authed_page, is_logged_in

    with authed_page() as page:
        if not is_logged_in(page):
            typer.echo("Not logged in — run `gr login` first (saves your browser session).")
            raise typer.Exit(1)
        ex = ActionExecutor(
            conn,
            GoodreadsGraphQLBackend(page),
            run_id=run_id,
            settings=settings,
            throttle=Throttle(),
            dry_run=False,
            stop_file=stop_file,
        )
        results = [_dispatch_write(ex, it) for it in items]
    live: Counter[str] = Counter(r.status for r in results)
    finish_run(conn, run_id, len(items), live.get("done", 0), live.get("failed", 0))
    typer.echo(
        f"apply (LIVE): {live.get('done', 0)} done · {live.get('failed', 0)} failed · "
        f"{live.get('skipped_idempotent', 0)} already-done · {capped} capped this run. "
        "`gr stop` halts mid-run; re-run to continue past the cap."
    )


@app.command()
def login() -> None:
    """One-time interactive Goodreads login; saves your browser session for live writes."""
    from gr_autopilot.browser.session import login as do_login

    do_login()
    typer.echo("Saved session. You can now `gr apply <plan.csv> --no-dry-run`.")


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
