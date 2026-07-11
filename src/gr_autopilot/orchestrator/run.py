from __future__ import annotations

import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from gr_autopilot.actions.core import GoodreadsBackend, Throttle
from gr_autopilot.actions.executor import ActionExecutor
from gr_autopilot.catalog.enrich import enrich_genres
from gr_autopilot.catalog.protocols import Catalog
from gr_autopilot.config import Settings
from gr_autopilot.generate.prompt import TargetBook
from gr_autopilot.store.repository import finish_run, start_run, targets
from gr_autopilot.voice.index import build_index
from gr_autopilot.voice.protocols import Embedder, VectorStore


@dataclass(frozen=True)
class RunSummary:
    run_id: int
    planned: int
    done: int
    failed: int
    dry_run: bool


def review_unreviewed(
    conn: sqlite3.Connection,
    *,
    generate_text: Callable[[TargetBook], str],
    backend: GoodreadsBackend,
    settings: Settings,
    dry_run: bool,
    throttle: Throttle | None = None,
    limit: int | None = None,
) -> RunSummary:
    """For each rated read-but-unreviewed book: generate a review and post it.

    `generate_text` is injected so the orchestrator is testable without an LLM.
    Capped at settings.max_actions_per_run. A failed action never aborts the run.
    """
    rows = targets(conn, settings.require_rating)
    cap = (
        settings.max_actions_per_run
        if limit is None
        else min(limit, settings.max_actions_per_run)
    )
    rows = rows[:cap]

    run_id = start_run(conn, "dry_run" if dry_run else "live")
    executor = ActionExecutor(
        conn,
        backend,
        run_id=run_id,
        settings=settings,
        throttle=throttle or Throttle(),
        dry_run=dry_run,
    )

    planned = done = failed = 0
    for row in rows:
        book = TargetBook(
            title=row["title"], author=row["author"], rating=row["my_rating"]
        )
        text = generate_text(book)
        planned += 1
        result = executor.post_review(row["book_id"], text, book.rating or 0)
        if result.status == "done":
            done += 1
        elif result.status == "failed":
            failed += 1

    finish_run(conn, run_id, planned, done, failed)
    return RunSummary(
        run_id=run_id, planned=planned, done=done, failed=failed, dry_run=dry_run
    )


def prepare_corpus(
    conn: sqlite3.Connection,
    *,
    embedder: Embedder,
    store: VectorStore,
    catalog: Catalog | None = None,
    enrich_limit: int | None = None,
) -> tuple[int, int]:
    """Optionally enrich genres, then (re)build the voice index.

    Returns (books_enriched, reviews_indexed). Pass catalog=None to skip enrichment
    (e.g. for an offline run). Genres enriched here flow into the index metadata so
    retrieval can filter by genre.
    """
    enriched = (
        enrich_genres(conn, catalog, limit=enrich_limit) if catalog is not None else 0
    )
    indexed = build_index(conn, embedder, store)
    return enriched, indexed
