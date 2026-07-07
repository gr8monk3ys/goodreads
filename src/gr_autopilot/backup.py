"""Back up the git-ignored personal artifacts (data/, drafts/) to a tarball.

These files are deliberately never committed — they're personal content — which
means git can't protect them. A worktree cleanup once deleted all of them. The
fix is a dumb, dependable tarball written somewhere outside the repo.
"""

from __future__ import annotations

import tarfile
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path


def backup_artifacts(sources: Sequence[Path], dest_dir: Path, *, timestamp: datetime) -> Path:
    """Tar the existing sources into dest_dir/gr-backup-YYYYMMDD-HHMMSS.tar.gz.

    Missing sources are skipped (a fresh clone may not have drafts yet); if
    nothing exists at all, that's a caller error — raise rather than write an
    empty archive that reads as a successful backup.
    """
    present = [src for src in sources if src.exists()]
    if not present:
        raise ValueError(f"nothing to back up: none of {[str(s) for s in sources]} exist")

    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / f"gr-backup-{timestamp:%Y%m%d-%H%M%S}.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        for src in present:
            tar.add(src, arcname=src.name)
    return archive
