import sqlite3
from pathlib import Path

import pytest

from gr_autopilot.drafts.format import DraftMeta, parse_draft
from gr_autopilot.drafts.studio import (
    has_draft,
    pending_target_rows,
    status_counts,
    write_draft,
)
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.store.repository import upsert_books

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def _meta(book_id: int = 1, title: str = "X") -> DraftMeta:
    return DraftMeta(book_id=book_id, title=title, author="A", my_rating=4)


def test_write_draft_creates_file(tmp_path: Path) -> None:
    path = write_draft(tmp_path, _meta(), "a first draft")
    assert path.exists()
    meta, body = parse_draft(path.read_text())
    assert meta.book_id == 1
    assert "a first draft" in body


def test_write_draft_refuses_to_clobber_user_edits(tmp_path: Path) -> None:
    write_draft(tmp_path, _meta(), "AI draft")
    # simulate the user editing the file, then a re-run trying to regenerate it
    path = next(tmp_path.glob("1-*.md"))
    path.write_text(path.read_text().replace("AI draft", "MY OWN WORDS"))
    with pytest.raises(FileExistsError):
        write_draft(tmp_path, _meta(), "AI draft v2")
    assert "MY OWN WORDS" in path.read_text()  # user's edit untouched
    assert has_draft(tmp_path, 1)


def test_status_counts_scans_directory(tmp_path: Path) -> None:
    write_draft(tmp_path, _meta(1), "d1")
    write_draft(tmp_path, _meta(2), "d2")
    p2 = next(tmp_path.glob("2-*.md"))
    p2.write_text(p2.read_text().replace("status: draft", "status: approved"))
    assert status_counts(tmp_path) == {"draft": 1, "approved": 1}


def test_status_counts_missing_dir_is_empty(tmp_path: Path) -> None:
    assert status_counts(tmp_path / "nope") == {}


def test_pending_targets_excludes_already_drafted(conn: sqlite3.Connection, tmp_path: Path) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    # fixture has exactly one read+rated+unreviewed target: book 22
    assert [r["book_id"] for r in pending_target_rows(conn, tmp_path)] == [22]
    write_draft(tmp_path, _meta(22, "Some Skim"), "draft for 22")
    assert pending_target_rows(conn, tmp_path) == []
