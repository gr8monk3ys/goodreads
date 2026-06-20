# goodreads-autopilot

Autonomous automation for a single Goodreads account: ingest your library, learn your
reviewing voice, generate new reviews with Claude, and write them back — reviews,
ratings, shelves/tags, want-to-read, and Listopia lists.

> **There is no Goodreads API** (retired 2020, fully dead by late 2025). All *writes* go
> through your logged-in browser session via Playwright. This is powerful but ToS-grey and
> carries real account-suspension risk; the suite runs fully autonomously but ships with a
> kill switch, dry-run, idempotency, and throttling underneath. See
> [the design spec](docs/superpowers/specs/2026-06-18-goodreads-autopilot-design.md).

## Architecture

```
ingest   CSV export  -> normalized records          (stdlib csv)
store    records      -> SQLite (books/reviews/shelves/runs/actions_log)
voice    reviews      -> embeddings + vector store   (bge-small + Chroma; protocol-based)
generate target book  -> review draft in your voice  (Claude RAG, prompt-cached)
catalog  book id      -> public genres / metadata     (no auth; __NEXT_DATA__ read)
browser  one-time login -> saved Playwright session  (storage_state + stealth)
actions  draft/shelf  -> Goodreads writes            (kill switch + idempotency + throttle)
orchestrator + cli     -> end-to-end workflows        (gr ingest | enrich | review | run | stop | status)
```

Each layer sits behind a typed interface, so the risky browser layer is quarantined and
everything above it is pure local data work — unit-tested without ever touching Goodreads.

## Status

| Layer | State |
|-------|-------|
| Foundation + CI quality gate (uv, ruff, mypy --strict, pytest, bandit) | ✅ built & green |
| ingest · store · voice · generate | ✅ built & green |
| catalog — public genre enrichment (`gr enrich`, no auth, live-verified) | ✅ built & green |
| actions safety spine · orchestrator · CLI (`stop`/`review`/`enrich`) | ✅ built & green (48 tests, ~97% coverage) |
| **Playwright write backend** | ⏳ needs your one-time [live capture](docs/superpowers/research/write-flows-capture-runbook.md) |
| Scheduled `automation.yml` + self-hosted residential runner | ⏳ planned |

## Install

```bash
uv sync                                    # core (ingest/store/orchestrator)
uv sync --extra voice --extra generate     # + embeddings + Claude generation
uv sync --extra browser                    # + Playwright (for writes)
```

## Quickstart

```bash
# 1. Export your library from Goodreads: My Books -> Import/Export -> Export Library
uv run gr ingest goodreads_library_export.csv
uv run gr status                           # books=... review_targets=...
uv run gr enrich                           # fetch genres for your books (public, no login)

# 2. (after installing voice+generate extras and ANTHROPIC_API_KEY) generate, dry-run
uv run gr review --dry-run --limit 1       # generates drafts, logs the writes it WOULD make

# 3. Kill switch any time
uv run gr stop                             # writes data/STOP, halts in-flight writes
```

## Enabling real writes

There is no API, so the write layer needs a one-time manual step from you — an interactive
login and a short DOM/endpoint capture. Follow
[the capture runbook](docs/superpowers/research/write-flows-capture-runbook.md), then
implement `src/gr_autopilot/actions/playwright_backend.py` against your captures.

## Safety

`GR_DISABLE_WRITES=1` and `gr stop` (a `data/STOP` sentinel) both block writes. Runs are
capped (`GR_MAX_ACTIONS_PER_RUN`, default 10), throttled with human-like delays, and every
action is logged to `actions_log` before execution; completed actions are never repeated.

## Development

```bash
uv run pytest          # tests + coverage gate (80%)
uv run ruff check .    # lint
uv run mypy            # strict type check
uv run bandit -c pyproject.toml -r src
```

## Credits

The read-only catalog layer uses the public-data technique from
[goodreads-mcp](https://github.com/shreeyachand/goodreads-mcp) — reading the embedded
`__NEXT_DATA__` JSON of public book pages. Reimplemented here (no dependency), credited with thanks.

GPL-3.0. Built with [Claude Code](https://claude.com/claude-code).
