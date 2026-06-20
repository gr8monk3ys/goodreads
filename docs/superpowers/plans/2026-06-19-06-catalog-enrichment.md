# goodreads-autopilot — Plan 06: Catalog Read-Enrichment

> **Status: BUILT & green + live-verified** (implemented 2026-06-19). Triggered by the user surfacing `goodreads-mcp`; investigation confirmed no write-capable library exists, but the read technique is worth adopting.

**Goal:** Add a credential-free read layer that enriches books with real genres (closing the spec's genre gap — the CSV export has no genre field) and resolves book metadata for the write flows.

**Why:** A landscape scan (top 30 by stars, 25 by recency, ~85 keyword-matched) confirmed every "Goodreads API" Python lib wraps the dead official OAuth API, and everything modern (incl. `goodreads-mcp`) is read-only by design. So the write path is unchanged — but `goodreads-mcp`'s technique (read the public book page's embedded `__NEXT_DATA__` JSON, no auth) is a clean, low-fragility read source.

**Architecture:** `Catalog` protocol; `GoodreadsPublicCatalog` fetches a public book page and `parse_book_meta` reads `apolloState` → `Book.bookGenres[].genre.name`. Parser **verified against live goodreads.com structure**; live HTTP adapter is integration-only (omitted from coverage). **Spec gap closed:** §6.3 genre filtering now has real genre data.

## Files
```
catalog/protocols.py        # BookMeta, Catalog protocol
catalog/parse.py            # extract_next_data, parse_book_meta (unit-tested vs verified structure)
catalog/goodreads_public.py # GoodreadsPublicCatalog live adapter (omit cov; live-verified manually)
catalog/enrich.py           # enrich_genres(conn, catalog) — idempotent
store/schema.sql            # + book_genres table; repository: books_without_genres, set_book_genres
voice/index.py              # genre wired into index metadata (genre-filtered retrieval)
cli.py                      # + gr enrich
tests/test_catalog.py, tests/test_voice.py (+genre), tests/test_cli.py (+enrich)
```

## Verification
- Unit: ruff clean · mypy `--strict` clean (43 files) · 48 tests · 97.45% coverage · bandit 0 medium/high.
- **Live end-to-end:** `GoodreadsPublicCatalog().get_meta(5907)` → "The Hobbit", genres `(Fantasy, Classics, Fiction, Adventure, Young Adult, …)`. The real adapter works, no credentials.

## Notes
This does NOT change the write path — `goodreads-mcp` and all modern libs are read-only; writes still require the session-based Playwright layer + the user's live capture. Credit: github.com/shreeyachand/goodreads-mcp.
