"""Render metrics + suggestions to a string. The only module that produces formatting.

Keeping every format here means a future `--html` renderer is an additive change and
nothing upstream (metrics/suggestions) has to know about presentation.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import asdict

from gr_autopilot.insights.metrics import LibraryMetrics
from gr_autopilot.insights.suggestions import Suggestion

_IMPACT_BADGE = {"high": "🔴 HIGH", "medium": "🟠 MED", "low": "🟡 LOW"}


def render(
    metrics: LibraryMetrics,
    suggestions: Sequence[Suggestion],
    fmt: str = "md",
    top: int = 10,
) -> str:
    if fmt == "md":
        return _markdown(metrics, suggestions, top)
    if fmt == "table":
        return _table(metrics, suggestions)
    if fmt == "json":
        return json.dumps(
            {"metrics": asdict(metrics), "suggestions": [asdict(s) for s in suggestions]},
            indent=2,
        )
    raise ValueError(f"unknown format: {fmt!r} (expected md|table|json)")


def _shelf_summary(counts: dict[str, int]) -> str:
    order = ["read", "currently-reading", "to-read"]
    labels = {"read": "read", "currently-reading": "reading", "to-read": "to-read"}
    parts = [f"{counts[s]} {labels[s]}" for s in order if s in counts]
    parts += [f"{n} {s}" for s, n in counts.items() if s not in order]
    return " · ".join(parts)


def _markdown(m: LibraryMetrics, suggestions: Sequence[Suggestion], top: int) -> str:
    r, c, t, p, e, pg = m.ratings, m.reviews, m.tbr, m.pace, m.eras, m.pages
    lines: list[str] = ["# 📚 Goodreads insights", ""]
    lines.append(f"**{m.total_books} books** — {_shelf_summary(m.shelf_counts)}")

    lines += ["", "## Ratings"]
    if r.n_rated:
        lines.append(f"- Rated **{r.n_rated} of {r.n_read}** read · mean **{r.mean}**")
        stars = " · ".join(f"{s}★ {r.histogram[s]}" for s in range(5, 0, -1))
        lines.append(f"- {stars}")
        if r.crowd_delta is not None:
            tilt = "harsher than" if r.harsher else "more generous than"
            lines.append(f"- You rate {r.crowd_delta:+.2f} ({tilt} the crowd)")
    else:
        lines.append("- No ratings yet")

    lines += ["", "## Review coverage",
              f"- {c.n_reviewed} reviewed · **{c.n_unreviewed} unreviewed** "
              f"({c.n_targets} rated & ready to draft)"]

    if p.reads_by_year:
        span = " · ".join(f"{y}:{n}" for y, n in p.reads_by_year)
        lines += ["", "## Reading pace", f"- {span}"]
        if p.n_missing_date:
            lines.append(f"- {p.n_missing_date} read books missing a Date Read")

    if e.by_band:
        span = " · ".join(f"{b}:{n}" for b, n in e.by_band)
        lines += ["", "## Publication eras", f"- {span}"]

    if pg.n_with_pages:
        lines += ["", "## Pages",
                  f"- {pg.total_pages:,} pages across {pg.n_with_pages} read · "
                  f"median {pg.median_pages}"]

    if m.authors:
        top_auth = " · ".join(f"{a} ({n})" for a, n in m.authors[:top])
        lines += ["", "## Most-read authors", f"- {top_auth}"]

    if m.genres.top:
        top_g = " · ".join(f"{g} ({n})" for g, n in m.genres.top[:top])
        lines += ["", "## Genres (read)", f"- {top_g}"]

    if t.size:
        lines += ["", "## To-read pile", f"- **{t.size} books**"]
        if t.peak_year is not None:
            lines.append(f"- peak intake: {t.peak_adds} added in {t.peak_year}")

    lines += ["", "## Suggested moves", ""]
    if suggestions:
        for s in suggestions:
            lines.append(f"### {_IMPACT_BADGE[s.impact]} · {s.title}  _( {s.goal} )_")
            lines.append(s.detail)
            for item in s.items[:top]:
                lines.append(f"- {item}")
            lines.append("")
    else:
        lines.append("_Nothing to suggest — ingest a library first (`gr ingest`)._")

    return "\n".join(lines).rstrip() + "\n"


def _table(m: LibraryMetrics, suggestions: Sequence[Suggestion]) -> str:
    r, c, t = m.ratings, m.reviews, m.tbr
    lines = [
        f"books={m.total_books} read={r.n_read} rated={r.n_rated} unrated={r.n_unrated} "
        f"unreviewed={c.n_unreviewed} tbr={t.size}",
        "suggestions:",
    ]
    for s in suggestions:
        lines.append(f"  [{s.impact:>6}] {s.key:<14} {s.title}")
    return "\n".join(lines) + "\n"
