# goodreads-insights — read-only library analytics & suggestions

**Date:** 2026-06-23
**Status:** Approved (design) — pending implementation plan
**Branch:** `claude/recursing-mendeleev-5e182b`

## Context

`gr_autopilot` ingests a Goodreads CSV export into SQLite and (eventually) writes
reviews/shelves back through a browser. Today nothing reads the stored data back out
*analytically* — the store is write-only from the user's perspective. The user wants to
make their Goodreads profile **better** along three axes they selected:

1. **Curation & shelves** — organize a sprawling library (their TBR is 349 books).
2. **Reading stats & insights** — understand their reading patterns.
3. **Discoverability & presence** — surface their signature and best work.

All three are served by one missing capability: a **read-only analytics layer** over the
existing store that reports stats *and* turns them into concrete, hand-applied
suggestions. Crucially this needs **zero account access** — it is a pure function of data
already on disk — so it carries none of the ToS/suspension risk of the write layer.

### Worked example (the user's current library, illustrative)

431 books: 75 read, 7 currently-reading, 349 to-read. 57 rated (mean 3.53, clustered at
3–4★, 4 five-stars), 15 written reviews. 60 read books have no review, 18 read books are
unrated, 42 read books have no `Date Read`. TBR added 69 (2023) / 65 (2024) / **214
(2025)**. These exact figures are what the metrics/suggestions below formalize.

## Goals

- A `gr insights` command that reports library analytics from the SQLite store.
- Concrete, prioritized **suggestions** (not just numbers), each tagged with the user goal
  it serves and described as a manual action — no writes are performed.
- Pure, isolated, fully unit-tested computation, matching the repo's existing layered
  architecture (typed interfaces, heavy/risky concerns quarantined).
- Output in Markdown (default), a compact terminal table, or JSON (for piping).
- Optional `--enrich` to add a **genre breakdown** by reusing the existing public catalog
  read path (still no login).

## Non-goals (explicit YAGNI for v1)

- **No writes.** Insights never touches a Goodreads account. Suggestions are advisory.
- **No HTML/dashboard export.** A `--html` one-pager is a deliberate future extension
  (see below), not v1.
- **No Claude narrative.** A `--narrative` flag over the `generate` layer is a future
  extension, not v1.
- **No new heavy dependencies.** Core insights uses only the stdlib + what's already
  installed. `--enrich` uses the already-present catalog path.

## How it serves the three goals

| User goal | What insights provides |
|-----------|------------------------|
| Reading stats & insights | Rating profile, reading pace by year, publication-era spread, page totals, author concentration, genre mix (`--enrich`). |
| Curation & shelves | TBR triage (size, add-velocity, age), author clusters that suggest themed shelves, custom-shelf coverage, data-hygiene fixes (missing dates). |
| Discoverability & presence | "Signature" summary (top genres/eras/authors), 5-star canon as a featured set, and the highest-impact gap-fill list (rate/review these to look active and considered). |

## Architecture

New package `src/gr_autopilot/insights/`, a pure **consumer** of the store — same
isolation discipline as `ingest`/`store`:

```
store (SQLite)
   |  read-only queries
   v
insights/metrics.py      pure functions: rows -> typed metric dataclasses
insights/suggestions.py  pure functions: metrics -> ranked Suggestion list (goal-tagged)
insights/report.py       metrics + suggestions -> Markdown | table | JSON string
   ^
cli.py  `gr insights [--format] [--enrich] [--top N]`
```

Data flow: `cli.insights` opens the DB (existing `_open_db`), optionally runs the existing
`enrich` path when `--enrich` is set, loads rows via small read-only repository helpers,
computes `LibraryMetrics`, derives `list[Suggestion]`, renders, and echoes. No mutation of
`books`/`reviews`/`shelves`; the only writes that can occur are genre rows from the
pre-existing `enrich` path under `--enrich`.

### Why these boundaries

- `metrics.py` is **pure data → data**: no I/O, no SQL, no formatting. Trivially testable
  with hand-built row lists; this is where correctness lives.
- `suggestions.py` is **metrics → advice**: thresholds and ranking, also pure. Testable by
  feeding synthetic metrics and asserting which suggestions fire.
- `report.py` is **the only place strings/format live**. Swapping Markdown for a future
  HTML renderer touches nothing else.
- Repository read helpers keep SQL in `store/`, consistent with the codebase.

## Data model change (minimal)

`BookRecord` and the store already persist review text (`reviews`, with the `is_empty`
generated column), custom shelves (`shelves`/`book_shelves`), ratings, avg rating, dates,
and genres (`book_genres`). **Only two fields are missing** and both are already in the
CSV:

- `Number of Pages` → `num_pages INTEGER` (nullable)
- `Original Publication Year` (fallback `Year Published`) → `original_pub_year INTEGER`
  (nullable)

Changes:

1. `csv_parser.BookRecord`: add `num_pages: int | None`, `original_pub_year: int | None`.
2. `csv_parser._row_to_record`: parse both via a tolerant int coercion (handles `""`,
   floats like `"1999.0"`, and non-numeric → `None`). `original_pub_year` prefers
   `Original Publication Year`, falls back to `Year Published`.
3. `store/schema.sql` `books`: add the two nullable columns. `CREATE TABLE IF NOT EXISTS`
   plus an additive migration helper so an existing `autopilot.db` gains the columns via
   `ALTER TABLE ... ADD COLUMN` guarded by a `PRAGMA table_info` check (idempotent).
4. `store/repository.upsert_books`: include the two columns in INSERT + `ON CONFLICT` SET.

Re-running `gr ingest` backfills the columns for existing rows (upsert is idempotent).

## Metrics catalog (`LibraryMetrics`)

Each is a pure function of the loaded rows. Shelf buckets are derived from
`exclusive_shelf` (`read` / `currently-reading` / `to-read`).

- **Shelf counts** — totals per exclusive shelf; overall count.
- **Rating profile** (read shelf, `my_rating > 0`): n rated, mean, star histogram
  (1–5), share unrated. If `avg_rating` is present, mean delta vs crowd and
  harsher/more-generous label; **absent gracefully** when the export omits Average Rating
  (this user's export does — see Edge Cases).
- **Review coverage**: read count, # with non-empty review (`reviews.is_empty = 0`), #
  unreviewed, # `targets()` (read + rated + unreviewed).
- **TBR shape**: size, adds-by-year (from `date_added`), add velocity (most recent full
  year vs prior), oldest add year, top stacked authors on the TBR.
- **Reading pace**: reads-by-year (from `date_read`), # read missing a `date_read`.
- **Publication eras**: histogram by decade from `original_pub_year`; BC years bucketed
  sensibly (see Edge Cases); # missing.
- **Page stats**: # read with a page count, total pages, median pages.
- **Author concentration** (read shelf): top authors by count.
- **Genres** (only when `--enrich` ran / `book_genres` populated): top genres on the read
  shelf, # read books still ungenred.

All histograms returned as ordered `list[tuple[key, count]]` for deterministic rendering.

## Suggestions catalog (`Suggestion`)

`Suggestion = {goal, title, detail, impact, items?}` where `goal ∈ {curation, stats,
presence}` and `impact ∈ {high, medium, low}`. Rules fire from thresholds on metrics;
output is **ranked by impact** then goal. All are advisory ("do X by hand"); none mutate
anything. v1 rules:

- **Fill rating gaps** (stats/presence, high if ≥10): "N read books are unrated" + the
  list — rating them makes the profile look considered.
- **Fill review gaps** (presence, high if ≥10): "N read books have no written review";
  surfaces the `targets()` list (read + rated, most recent first) as the best candidates,
  and notes `gr review --dry-run` can draft them.
- **TBR triage** (curation, high if TBR > 150 or add-velocity > read-rate × 10): reports
  the imbalance ("added 214 in 2025, read ~4/yr") and recommends a prune/shortlist pass;
  lists the top stacked authors as natural starting clusters.
- **Author shelves** (curation, medium): authors with ≥3 books across shelves are
  candidates for a dedicated shelf/reading project (e.g. "Poe ×10").
- **Date hygiene** (curation/stats, medium if ≥10): "N read books lack a Date Read — they
  don't count toward yearly stats or challenges"; suggests backfilling.
- **Signature** (presence, always): one-line identity from top genres (if enriched), top
  eras, and the 5-star list — the user's "what I'm known for," ready to feature.

Thresholds live as named constants in `suggestions.py` so they're easy to tune and test.

## CLI surface

```
gr insights [--format md|table|json] [--enrich] [--top N]
```

- `--format` default `md`. `table` = compact terminal summary; `json` = the full
  `LibraryMetrics` + suggestions for piping.
- `--enrich` runs the existing genre enrichment first (network, public read, no login),
  then includes the genre breakdown. Off by default to keep the command instant/offline.
- `--top` caps list lengths in suggestions/author tables (default 10).

Follows the existing typer pattern: lazy imports for the enrich path, `_open_db(settings)`.

## Testing strategy

- `metrics.py`: unit tests with hand-built `BookRecord`/row lists covering each metric,
  including empty library, all-unrated, no-dates, BC publication years, and an export
  **without** an Average Rating column (must not crash; crowd-delta omitted).
- `suggestions.py`: feed synthetic `LibraryMetrics`, assert exactly which rules fire and
  their ranking at boundary thresholds.
- `report.py`: golden-ish assertions that each format includes the expected sections and
  that JSON round-trips to the same numbers.
- `cli`: `CliRunner` test of `gr insights` over the existing `sample_export.csv` fixture,
  asserting exit 0 and key sections. `--enrich` path mocked (no live network in CI),
  consistent with how the catalog layer is already tested.
- Maintain the repo's gates: `ruff`, `mypy --strict`, `bandit`, and the 80% coverage
  floor. `report.py` rendering and any network adapter stay out of the coverage `omit`
  list only if they're pure; the enrich network call is already excluded.

## Edge cases / data-shape handling

- **No `Average Rating` column.** This user's export omits it. `_row_to_record` already
  yields `avg_rating=None`; metrics must treat the crowd-delta block as optional and the
  report must skip it cleanly.
- **BC publication years.** Plato et al. produce negative years (e.g. −350). Decade
  bucketing must not crash; bucket all pre-1500 into a single "pre-1500 / classical"
  band rather than emit `-430s`.
- **Spreadsheet-formula wrappers** (`="..."`) — already handled by `clean_isbn`; the two
  new numeric fields use tolerant coercion that ignores any non-numeric content.
- **Missing dates** are first-class signal (a suggestion), not an error.
- **Empty / freshly-migrated DB.** `gr insights` on an empty store prints a friendly
  "ingest first" message (mirrors `status` returning zeros), not a traceback.
- **Old DB without the new columns.** The additive migration adds them; pre-backfill rows
  read as `NULL` and are counted as "missing" until the next `gr ingest`.

## Future extensions (out of scope for v1, designed to bolt on)

- **`--html`**: a self-contained one-pager (the `report.py` boundary makes this a new
  renderer only) — best serves "presence" as a shareable artifact.
- **`--narrative`**: pass `LibraryMetrics` to the existing `generate` layer for a
  Claude-written reading profile; needs `ANTHROPIC_API_KEY` + the `generate` extra.
- **Trend over time**: snapshot metrics per `runs` row to chart change between exports.

## Risks

- **None to the account.** Read-only; no browser, no writes. The only network is the
  optional, pre-existing public genre read under `--enrich`.
- **Suggestion quality** is threshold-driven and could mis-rank for unusual libraries;
  thresholds are centralized constants and covered by boundary tests, and every
  suggestion is advisory so a bad rank costs nothing but noise.
```
