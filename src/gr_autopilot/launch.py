"""Sequence the action board into a launch campaign. Pure: BookFacts -> a phased plan.

Where `dashboard` shows *everything* to do, `launch` answers *what to do first, and at what
cadence*. Goodreads' activity feed is proprietary, so this is a reasoned bet, not a known
rule: dumping 60 reviews in one day tends to get collapsed or down-weighted in followers'
feeds (and can read as automated), while spreading them out — a few a week, led by the books
you feel strongest about — is likelier to keep each one visible. The ordering here is a
heuristic, not a guarantee. Read-only.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from math import ceil

from gr_autopilot.curate import hygiene
from gr_autopilot.insights.metrics import BookFact
from gr_autopilot.presence import signature

READ = "read"
_DEFAULT_CADENCE = 3


def ranked_review_targets(facts: Sequence[BookFact], drafted_ids: set[int]) -> list[BookFact]:
    """Unreviewed read books, ranked so the easiest, strongest ones come first.

    A ready draft leads (you can act today), then how much you loved it (`my_rating`), then a
    gentle lean toward broadly well-rated books (`avg_rating`), then title for a stable order.
    Note: `avg_rating` is the crowd's mean score, not readership — the export carries no
    ratings count, so this orders by taste, not reach.
    """
    targets = [f for f in facts if f.exclusive_shelf == READ and not f.has_review]
    return sorted(
        targets,
        key=lambda f: (
            0 if f.book_id in drafted_ids else 1,
            -f.my_rating,
            -(f.avg_rating or 0.0),
            f.title,
        ),
    )


@dataclass(frozen=True)
class LaunchStep:
    text: str
    detail: str = ""


@dataclass(frozen=True)
class LaunchPhase:
    key: str
    title: str
    blurb: str
    steps: tuple[LaunchStep, ...]


@dataclass(frozen=True)
class LaunchPlan:
    phases: tuple[LaunchPhase, ...]
    reviews_per_week: int
    weeks_to_finish: int
    n_review_targets: int

    def phase(self, key: str) -> LaunchPhase:
        return next(p for p in self.phases if p.key == key)


def _review_step(f: BookFact, drafted_ids: set[int]) -> LaunchStep:
    stars = f"{f.my_rating}★" if f.my_rating else "unrated"
    detail = "draft ready in drafts/reviews/" if f.book_id in drafted_ids else "needs a draft"
    return LaunchStep(f"Post: {f.title} — {f.author} ({stars})", detail)


def build_launch_plan(
    facts: Sequence[BookFact],
    *,
    drafted_ids: set[int],
    bio: str = "",
    reviews_per_week: int = _DEFAULT_CADENCE,
) -> LaunchPlan:
    """Turn the flat action board into a prioritized, paced rollout campaign."""
    cadence = max(1, reviews_per_week)
    hyg = hygiene(facts)
    sig = signature(facts)
    read = [f for f in facts if f.exclusive_shelf == READ]
    members = [f for f in read if f.my_rating == 5]
    targets = ranked_review_targets(facts, drafted_ids)
    weeks_to_finish = ceil(len(targets) / cadence) if targets else 0

    # 1 · Today — one-time polish that makes the profile read "complete" at a glance.
    today: list[LaunchStep] = []
    if bio:
        today.append(LaunchStep("Paste your bio into Settings → Profile", bio))
    today.append(
        LaunchStep(
            f"Create the existential-classics shelf and feature it ({len(members)} books ready)",
            "Your 5★ canon is the spine of it.",
        )
    )
    if hyg.unrated_reads:
        today.append(
            LaunchStep(
                f"Rate your {len(hyg.unrated_reads)} unrated reads",
                "`gr apply` can do this through the safe spine, or tick them by hand.",
            )
        )
    if hyg.undated_reads:
        today.append(
            LaunchStep(
                f"Backfill read-years on {len(hyg.undated_reads)} books",
                "Even just the year fixes your stats and Reading Challenge.",
            )
        )

    # 2 · This week — the follow-conversion engine: your strongest reviews + first follows.
    this_week = [_review_step(f, drafted_ids) for f in targets[:cadence]]
    this_week.append(
        LaunchStep(
            "Follow ~10 reviewers from those books' Community Reviews",
            "Pick people whose reviews you actually like — some follow back, but do it for the "
            "feed you'll get, not the reciprocity.",
        )
    )

    # 3 · Cadence — the remaining reviews, paced so each gets its own feed slot.
    cadence_steps = [_review_step(f, drafted_ids) for f in targets[cadence:]]

    # 4 · Ongoing — the weekly habit that compounds presence.
    ongoing = [
        LaunchStep(f"Each week: post your next ~{cadence} reviews from the list above"),
        LaunchStep("Each week: like + leave one real comment on a review of a book you've read"),
        LaunchStep("Keep your Reading Challenge count updated as you log books"),
    ]

    canon = ", ".join(sig.five_star_titles[:3]) or "your standout reads"
    phases = (
        LaunchPhase(
            "today",
            "Today — 30 minutes to a complete-looking profile",
            f"A reader of {canon}. Do these once and the empty-profile look is gone.",
            tuple(today),
        ),
        LaunchPhase(
            "this_week",
            "This week — your strongest reviews",
            "Lead with the ones you feel strongest about — your best shot at turning "
            "someone who lands on a book's page into a follower.",
            tuple(this_week),
        ),
        LaunchPhase(
            "cadence",
            f"Weeks 2+ — steady cadence (~{cadence}/week)",
            f"At ~{cadence}/week you're through the backlog in ~{weeks_to_finish} weeks. "
            "The point isn't speed — it's staying visible week to week instead of going "
            "quiet.",
            tuple(cadence_steps),
        ),
        LaunchPhase(
            "ongoing",
            "Ongoing — the weekly habit",
            "A profile that's active most weeks beats one that did everything in a "
            "weekend and went silent.",
            tuple(ongoing),
        ),
    )
    return LaunchPlan(
        phases=phases,
        reviews_per_week=cadence,
        weeks_to_finish=weeks_to_finish,
        n_review_targets=len(targets),
    )


def render_markdown(plan: LaunchPlan) -> str:
    lines = ["# 🚀 Your Goodreads launch plan", ""]
    lines.append(
        f"_{plan.n_review_targets} reviews to write · ~{plan.reviews_per_week}/week · "
        f"caught up in ~{plan.weeks_to_finish} weeks._"
    )
    for p in plan.phases:
        lines += ["", f"## {p.title}", "", f"_{p.blurb}_", ""]
        for s in p.steps:
            lines.append(f"- [ ] {s.text}" + (f"  \n      {s.detail}" if s.detail else ""))
    return "\n".join(lines)
