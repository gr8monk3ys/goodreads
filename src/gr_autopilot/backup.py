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

    Sources are derived from GR_* config, so a wrong derivation must fail loudly
    here rather than produce a silently wrong archive: refuse sources broad
    enough to sweep up credentials (cwd/home/root), a dest inside a source
    (the archive would tar itself), basename collisions (restore would merge
    two trees), and clobbering an existing archive.
    """
    broad = (Path.cwd(), Path.home())
    present: list[Path] = []
    seen: set[Path] = set()
    for src in sources:
        if not src.exists():
            continue
        resolved = src.resolve()
        if resolved in broad or resolved == Path(resolved.anchor):
            raise ValueError(f"refusing to back up {src}: too broad (resolves to {resolved})")
        if resolved not in seen:
            seen.add(resolved)
            present.append(src)
    if not present:
        raise ValueError(f"nothing to back up: none of {[str(s) for s in sources]} exist")

    names = [src.name for src in present]
    if len(set(names)) != len(names):
        raise ValueError(
            f"source basenames collide ({', '.join(names)}): a restore would merge them"
        )

    for inner in seen:
        for outer in seen:
            if inner != outer and inner.is_relative_to(outer):
                raise ValueError(f"source {inner} is inside source {outer}: it would archive twice")

    resolved_dest = dest_dir.resolve()
    for outer in seen:
        if resolved_dest.is_relative_to(outer):
            raise ValueError(f"dest {dest_dir} is inside source {outer}: archive would tar itself")

    dest_dir.mkdir(parents=True, exist_ok=True)
    archive = dest_dir / f"gr-backup-{timestamp:%Y%m%d-%H%M%S}.tar.gz"
    with tarfile.open(archive, "x:gz") as tar:
        for src in present:
            tar.add(src, arcname=src.name)
    return archive
