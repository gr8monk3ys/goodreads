# Roadmap — toward a top-1% Goodreads profile (loop backbone)

**Owner loop goal (user, 2026-06-23):** "Don't stop until we have a profile in the top 1%
of Goodreads users." Reviews may be AI-*drafted* but the user stays in the loop —
**drafts only, the user edits in their own words and approves before anything is posted.**

This file is the durable source of truth for the autonomous `/loop`. Every iteration:
read this, do the next unchecked thing, update status + the changelog at the bottom,
commit. If context was summarized, this file + git log are how to resume.

## Honest framing

Reaching literal "top 1%" depends partly on levers only the user controls. Split:

- **Automatable here (the loop owns these):** read-only analytics + a prioritized action
  plan; AI-drafted reviews for the 60 unreviewed reads (human-edited); completing the 18
  unrated ratings; a real shelf taxonomy; TBR triage; data-hygiene (42 missing dates); a
  presence/bio pack.
- **Only the user can do (the loop hands off a tight checklist):** actually *posting*
  edited reviews/ratings/shelves to Goodreads (also the ToS/suspension-risk write path,
  deferred by user's "safe analyzer first" choice); reading more books; social engagement
  (followers, friends, likes, comments) which drives "top reviewer" status.

The loop maximizes the first set and produces everything the user needs for the second.

## Baseline (from the user's real export, 2026-06-23)

431 books — 75 read, 7 reading, 349 to-read. 57 rated (mean 3.53, only 4×5★), 15 written
reviews. Gaps: 60 reads unreviewed, 18 reads unrated, 42 reads missing a Date Read. TBR
add velocity exploding (69→65→**214** in 2023→24→25). Signature: philosophical classics
(5★: Notes from Underground, Siddhartha, Brave New World, Man's Search for Meaning).

## Sub-projects

Each is spec → plan → TDD build → run → commit. Status: ☐ todo · ◐ in progress · ☑ done.

- **SP1 — Insights analyzer** ◐
  Read-only `gr insights` (metrics + goal-tagged suggestions). Spec:
  `specs/2026-06-23-goodreads-insights-design.md` (approved). → build + run on real data,
  emit the prioritized "path to top 1%" action plan.

- **SP2 — Draft-review studio** ☐
  Generate review drafts (Claude RAG in the user's voice, prompt-cached) for the 60
  unreviewed reads. Output: editable Markdown drafts in `drafts/reviews/` with a status
  header (draft → approved). **Never posts.** A review is "done" only when the user marks
  it approved after editing. Needs `generate`+`voice` extras + `ANTHROPIC_API_KEY`.

- **SP3 — Curation toolkit** ☐
  Shelf taxonomy proposal (from genres + author clusters), TBR triage into priority tiers,
  data-hygiene report (missing dates / unrated). Output: a plan the user applies (or, later
  and only with explicit go-ahead, an optional automated write path).

- **SP4 — Presence pack** ☐
  "Signature" summary, featured-shelf recommendation, profile-bio draft, and a "best
  reviews to feature" selection. Markdown the user can paste into their profile.

- **SP5 — Write-back (OPTIONAL, gated, risky)** ☐
  The Playwright path to actually apply *approved, non-review* changes (ratings, shelves,
  dates) under the existing kill-switch/dry-run/throttle. Requires explicit user go-ahead
  and a one-time login capture. Reviews are excluded by user's human-in-the-loop rule.

## Hard constraints (do not violate in any iteration)

1. **No review is ever auto-posted.** Drafts only; user edits + approves.
2. **No account writes** without explicit, in-the-moment user go-ahead (SP5 only).
3. Personal data (`goodreads_library_export.csv`, `data/`) stays git-ignored.
4. Every change keeps the gates green: `ruff`, `mypy --strict`, `bandit`, ≥80% coverage.

## Changelog

- 2026-06-23 — Roadmap created. SP1 spec approved + committed. Loop started.
