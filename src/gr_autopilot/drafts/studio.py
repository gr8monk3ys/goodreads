"""Persist and track review drafts on disk. The studio never posts and never clobbers.

Safety stance: `write_draft` refuses to overwrite an existing draft unless explicitly told
to, so a regeneration pass can never destroy edits the user has already made. Status
(draft/approved) lives in each file's frontmatter; nothing here talks to Goodreads.
"""

from __future__ import annotations

import sqlite3
from collections import Counter
from pathlib import Path

from gr_autopilot.drafts.format import DraftMeta, parse_draft, render_draft, slug
from gr_autopilot.store.repository import targets


def draft_path(drafts_dir: Path, meta: DraftMeta) -> Path:
    return drafts_dir / f"{meta.book_id}-{slug(meta.title)}.md"


def has_draft(drafts_dir: Path, book_id: int) -> bool:
    """True if any draft file already exists for this book."""
    return book_id in drafted_book_ids(drafts_dir)


def drafted_book_ids(drafts_dir: Path) -> set[int]:
    """Book ids that already have a draft file, from a single directory scan.

    The one definition of "has a draft" — every other check routes through it,
    so dashboard, launch, and the clobber guard can't drift apart on the
    filename convention. Missing dir -> empty.
    """
    ids: set[int] = set()
    if drafts_dir.is_dir():
        for path in drafts_dir.glob("*.md"):
            prefix = path.name.partition("-")[0]
            if prefix.isdigit():
                ids.add(int(prefix))
    return ids


def posted_book_ids(drafts_dir: Path) -> set[int]:
    """Book ids whose draft frontmatter says `status: posted`.

    The DB only learns a review went live on the next export/ingest; between
    posting and that ingest, the draft files are the fresher source. Missing
    dir -> empty.
    """
    if not drafts_dir.is_dir():
        return set()
    ids: set[int] = set()
    for path in sorted(drafts_dir.glob("*.md")):
        meta, _ = parse_draft(path.read_text(encoding="utf-8"))
        if meta.status == "posted":
            ids.add(meta.book_id)
    return ids


def write_draft(drafts_dir: Path, meta: DraftMeta, body: str, *, overwrite: bool = False) -> Path:
    drafts_dir.mkdir(parents=True, exist_ok=True)
    if not overwrite and has_draft(drafts_dir, meta.book_id):
        raise FileExistsError(f"draft for book {meta.book_id} exists; refusing to clobber edits")
    path = draft_path(drafts_dir, meta)
    path.write_text(render_draft(meta, body), encoding="utf-8")
    return path


def status_counts(drafts_dir: Path) -> dict[str, int]:
    """Count drafts by status across the directory. Missing dir -> empty."""
    if not drafts_dir.is_dir():
        return {}
    counts: Counter[str] = Counter()
    for path in sorted(drafts_dir.glob("*.md")):
        meta, _ = parse_draft(path.read_text(encoding="utf-8"))
        counts[meta.status] += 1
    return dict(counts)


def pending_target_rows(
    conn: sqlite3.Connection, drafts_dir: Path, require_rating: bool = True
) -> list[sqlite3.Row]:
    """Read+unreviewed books that don't yet have a draft file — the worklist to generate."""
    drafted = drafted_book_ids(drafts_dir)
    return [r for r in targets(conn, require_rating) if int(r["book_id"]) not in drafted]
