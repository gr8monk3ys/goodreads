"""The backup layer exists because a worktree cleanup once destroyed every
git-ignored artifact (DB, drafts). It tars data/ + drafts/ into a timestamped
archive somewhere OUTSIDE the repo, so the personal content survives anything
that happens to the checkout."""

from __future__ import annotations

import tarfile
from datetime import datetime
from pathlib import Path

import pytest

from gr_autopilot.backup import backup_artifacts

STAMP = datetime(2026, 7, 6, 12, 30, 5)


def _seed(root: Path) -> list[Path]:
    data = root / "data"
    drafts = root / "drafts" / "reviews"
    data.mkdir(parents=True)
    drafts.mkdir(parents=True)
    (data / "autopilot.db").write_bytes(b"sqlite bytes")
    (drafts / "1-book.md").write_text("draft body")
    return [data, root / "drafts"]


def test_backup_creates_timestamped_archive(tmp_path: Path) -> None:
    sources = _seed(tmp_path / "repo")
    dest = tmp_path / "backups"

    archive = backup_artifacts(sources, dest, timestamp=STAMP)

    assert archive == dest / "gr-backup-20260706-123005.tar.gz"
    assert archive.is_file()


def test_backup_archive_contains_source_trees(tmp_path: Path) -> None:
    sources = _seed(tmp_path / "repo")

    archive = backup_artifacts(sources, tmp_path / "backups", timestamp=STAMP)

    with tarfile.open(archive) as tar:
        names = set(tar.getnames())
    assert "data/autopilot.db" in names
    assert "drafts/reviews/1-book.md" in names


def test_backup_skips_missing_sources(tmp_path: Path) -> None:
    sources = _seed(tmp_path / "repo")
    missing = tmp_path / "repo" / "nope"

    archive = backup_artifacts(
        [*sources, missing], tmp_path / "backups", timestamp=STAMP
    )

    with tarfile.open(archive) as tar:
        assert not any(n.startswith("nope") for n in tar.getnames())


def test_backup_raises_when_nothing_exists(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="nothing to back up"):
        backup_artifacts([tmp_path / "ghost"], tmp_path / "backups", timestamp=STAMP)


def test_backup_creates_dest_dir(tmp_path: Path) -> None:
    sources = _seed(tmp_path / "repo")
    dest = tmp_path / "deep" / "nested" / "backups"

    archive = backup_artifacts(sources, dest, timestamp=STAMP)

    assert archive.parent == dest
    assert archive.is_file()


def test_backup_restores_faithfully(tmp_path: Path) -> None:
    """Round-trip: extract the archive and get byte-identical files back."""
    sources = _seed(tmp_path / "repo")

    archive = backup_artifacts(sources, tmp_path / "backups", timestamp=STAMP)

    out = tmp_path / "restore"
    with tarfile.open(archive) as tar:
        tar.extractall(out, filter="data")
    assert (out / "data" / "autopilot.db").read_bytes() == b"sqlite bytes"
    assert (out / "drafts" / "reviews" / "1-book.md").read_text() == "draft body"
