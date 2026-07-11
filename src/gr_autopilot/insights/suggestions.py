"""Turn metrics into ranked, goal-tagged advice. Pure: LibraryMetrics -> list[Suggestion].

Every suggestion is advisory and describes a *manual* action — nothing here writes to an
account. Thresholds are named constants so they are easy to tune and test at the boundary.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from gr_autopilot.insights.metrics import LibraryMetrics

# Tunable thresholds.
RATING_GAP_HIGH = 10
REVIEW_GAP_HIGH = 10
TBR_BIG = 150
TBR_VELOCITY_RATIO = 10  # recent adds > read-rate * this => the pile is outrunning you
AUTHOR_MIN = 3
DATE_HYGIENE_MEDIUM = 10

IMPACT_RANK = {"high": 0, "medium": 1, "low": 2}
GOAL_RANK = {"curation": 0, "stats": 1, "presence": 2}


@dataclass(frozen=True)
class Suggestion:
    key: str  # stable identifier (rating_gap, review_gap, tbr_triage, ...)
    goal: str  # curation | stats | presence
    impact: str  # high | medium | low
    title: str
    detail: str
    items: tuple[str, ...] = field(default_factory=tuple)


def _recent_read_rate(reads_by_year: list[tuple[int, int]]) -> float:
    if not reads_by_year:
        return 0.0
    recent = [count for _, count in reads_by_year[-3:]]
    return sum(recent) / len(recent)


def suggest(m: LibraryMetrics, top: int = 10) -> list[Suggestion]:
    out: list[Suggestion] = []

    if m.ratings.n_unrated > 0:
        impact = "high" if m.ratings.n_unrated >= RATING_GAP_HIGH else "medium"
        out.append(
            Suggestion(
                key="rating_gap",
                goal="stats",
                impact=impact,
                title=f"Rate {m.ratings.n_unrated} read books you never scored",
                detail="Unrated reads leave your taste illegible. Rating them is the fastest, "
                "lowest-effort lever on how considered your profile looks.",
            )
        )

    if m.reviews.n_unreviewed > 0:
        impact = "high" if m.reviews.n_unreviewed >= REVIEW_GAP_HIGH else "medium"
        out.append(
            Suggestion(
                key="review_gap",
                goal="presence",
                impact=impact,
                title=f"Write reviews for {m.reviews.n_unreviewed} read books",
                detail=f"{m.reviews.n_targets} are already rated — the best draft candidates. "
                "`gr review --dry-run` drafts them in your voice; you edit and approve "
                "before anything is posted.",
            )
        )

    read_rate = _recent_read_rate(m.pace.reads_by_year)
    outrunning = m.tbr.peak_adds > read_rate * TBR_VELOCITY_RATIO
    if m.tbr.size > TBR_BIG or outrunning:
        impact = "high" if m.tbr.size > TBR_BIG else "medium"
        pace_note = (
            f" You added {m.tbr.peak_adds} in {m.tbr.peak_year} alone but read ~{read_rate:.0f}/yr."
            if m.tbr.peak_year is not None and read_rate
            else ""
        )
        out.append(
            Suggestion(
                key="tbr_triage",
                goal="curation",
                impact=impact,
                title=f"Triage a {m.tbr.size}-book to-read pile",
                detail="A pile this size reads as clutter, not curation. Shortlist a near-term "
                "tier and let the rest be aspirational." + pace_note,
                items=tuple(f"{a} ({n})" for a, n in m.tbr.authors[:top]),
            )
        )

    combined: Counter[str] = Counter()
    for author, n in m.authors:
        combined[author] += n
    for author, n in m.tbr.authors:
        combined[author] += n
    stacked = [(a, n) for a, n in combined.most_common() if n >= AUTHOR_MIN]
    if stacked:
        out.append(
            Suggestion(
                key="author_shelves",
                goal="curation",
                impact="medium",
                title=f"Turn {len(stacked)} stacked authors into shelves or reading projects",
                detail="Authors you own/read in bulk are natural custom shelves — instant "
                "structure and a signal of what you go deep on.",
                items=tuple(f"{a} ({n} books)" for a, n in stacked[:top]),
            )
        )

    if m.pace.n_missing_date > 0:
        impact = "medium" if m.pace.n_missing_date >= DATE_HYGIENE_MEDIUM else "low"
        out.append(
            Suggestion(
                key="date_hygiene",
                goal="curation",
                impact=impact,
                title=f"Backfill Date Read for {m.pace.n_missing_date} books",
                detail="Undated reads are invisible to your yearly stats and the Reading "
                "Challenge — they make you look less active than you are.",
            )
        )

    if m.ratings.n_read > 0:
        five = m.ratings.histogram.get(5, 0)
        bits = []
        if m.genres.top:
            bits.append("top genres " + ", ".join(g for g, _ in m.genres.top[:3]))
        if m.eras.by_band:
            bits.append("you range from " + m.eras.by_band[0][0] + " to " + m.eras.by_band[-1][0])
        if five:
            bits.append(f"{five} five-star favorites to feature")
        out.append(
            Suggestion(
                key="signature",
                goal="presence",
                impact="low",
                title="Lead with your reading signature",
                detail="Make the profile say what you're about at a glance: "
                + ("; ".join(bits) if bits else "your standout reads and genres")
                + ".",
            )
        )

    out.sort(key=lambda s: (IMPACT_RANK[s.impact], GOAL_RANK[s.goal], s.key))
    return out
