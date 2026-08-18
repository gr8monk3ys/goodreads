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

    archive = backup_artifacts([*sources, missing], tmp_path / "backups", timestamp=STAMP)

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


def test_backup_refuses_overly_broad_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A source resolving to cwd (bare-filename GR_DB_PATH -> parent '.') must be refused,
    not silently tar the whole working tree (.git, session credentials, everything)."""
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)
    with pytest.raises(ValueError, match="too broad"):
        backup_artifacts([Path(".")], tmp_path / "backups", timestamp=STAMP)


def test_backup_refuses_home_directory_source(tmp_path: Path) -> None:
    """GR_DRAFTS_DIR=~/drafts derives home as the source — refuse before walking it."""
    with pytest.raises(ValueError, match="too broad"):
        backup_artifacts([Path.home()], tmp_path / "backups", timestamp=STAMP)


def test_backup_refuses_dest_inside_source(tmp_path: Path) -> None:
    """dest inside a source tars the half-written archive into itself and nests
    every prior backup into the next one."""
    sources = _seed(tmp_path / "repo")
    with pytest.raises(ValueError, match="inside"):
        backup_artifacts(sources, sources[0] / "backups", timestamp=STAMP)


def test_backup_refuses_arcname_collision(tmp_path: Path) -> None:
    """Two distinct sources sharing a basename would silently merge on restore."""
    a = tmp_path / "one" / "data"
    b = tmp_path / "two" / "data"
    a.mkdir(parents=True)
    b.mkdir(parents=True)
    (a / "f.txt").write_text("a")
    (b / "f.txt").write_text("b")
    with pytest.raises(ValueError, match="collide"):
        backup_artifacts([a, b], tmp_path / "backups", timestamp=STAMP)


def test_backup_refuses_nested_sources(tmp_path: Path) -> None:
    """A source inside another source would be archived twice under two arcnames."""
    sources = _seed(tmp_path / "repo")
    sub = sources[0] / "sub"
    sub.mkdir()
    with pytest.raises(ValueError, match="inside"):
        backup_artifacts([*sources, sub], tmp_path / "backups", timestamp=STAMP)


def test_backup_dedupes_identical_sources(tmp_path: Path) -> None:
    """The same directory configured twice must be archived once, not doubled."""
    sources = _seed(tmp_path / "repo")

    archive = backup_artifacts([sources[0], sources[0]], tmp_path / "backups", timestamp=STAMP)

    with tarfile.open(archive) as tar:
        names = tar.getnames()
    assert names.count("data/autopilot.db") == 1


def test_backup_refuses_to_clobber_existing_archive(tmp_path: Path) -> None:
    """Two runs in the same second must not truncate the first archive."""
    sources = _seed(tmp_path / "repo")
    backup_artifacts(sources, tmp_path / "backups", timestamp=STAMP)
    with pytest.raises(FileExistsError):
        backup_artifacts(sources, tmp_path / "backups", timestamp=STAMP)


def test_backup_restores_faithfully(tmp_path: Path) -> None:
    """Round-trip: extract the archive and get byte-identical files back."""
    sources = _seed(tmp_path / "repo")

    archive = backup_artifacts(sources, tmp_path / "backups", timestamp=STAMP)

    out = tmp_path / "restore"
    with tarfile.open(archive) as tar:
        tar.extractall(out, filter="data")
    assert (out / "data" / "autopilot.db").read_bytes() == b"sqlite bytes"
    assert (out / "drafts" / "reviews" / "1-book.md").read_text() == "draft body"
