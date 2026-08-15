# Bulk shelving via the classic Batch Edit UI

> Executed 2026-08-15 against the live account (user_id 168274083). Every step
> below was run, and the counts quoted are what the shelf page reported on reload.
> This is the cheapest known way to move many books at once: it needs no JWT, no
> GraphQL contract, and no stealth — it is the 2011-era Rails UI, still shipping.

Related: `write-flows-captured.md` covers the AppSync/GraphQL path for
single-book writes. Prefer *this* page when the operation is "many books, one
shelf"; prefer that one when it is "one book, precise state".

## The core loop

```
https://www.goodreads.com/review/list/<user_id>?view=table&per_page=100&<filter>
```

1. **Navigate** with `per_page=100` and whatever filter selects the books.
2. **Click `Batch Edit`** (top-right, ~`(914, 73)` at 1568px wide).
3. **Screenshot and confirm the panel is actually open** — see the toggle trap below.
4. **`select all`** (~`(632, 124)`), or tick individual row checkboxes at `x≈622`.
5. **Set the `Shelf:` dropdown** to the target shelf.
6. **Screenshot again** — confirm the rows are highlighted *and* the dropdown
   reads the shelf you meant.
7. **Click `add books to this shelf`** (~`(805, 95)`).
8. **Verify by reloading `/shelf/edit`** and reading the count.

100 books move in a single UI action — the underlying request count was not
inspected. It takes 30–60s to settle, and the page is unresponsive to script
injection while it does.

## Two filters that do the heavy lifting

**By author** — `&search[query]=<author>`. Gives a handful of rows; usually
`select all` is right, but read the titles first (see over-matching below).

**By publication date** — `&sort=date_pub&order=a` (or `d`). This is the trick
that makes era shelves possible: sort the whole library by publication date,
take a page of 100, and every row on it falls in one era.

Boundaries observed in this library:

| Sort | Page | Span | Used for |
|---|---|---|---|
| `date_pub` asc | 1 | −1800 → 1879 | `classics` |
| `date_pub` asc | 2 | 1881 → ~1946 | *straddles 1900 — skipped* |
| `date_pub` asc | 3 | 1947 → 1961 | `20th-century` |
| `date_pub` desc | 1 | 2025 → Jul 2005 | `21st-century` |

**Check the first and last row of the page before clicking add.** A page that
straddles an era boundary needs individual ticks, not `select all`.

## Traps, each of which cost a real mistake

### Unknown publication dates sort to the *front* of an ascending sort

The ascending `date_pub` page 1 is not "the oldest 100 books" — it is "every
book with no publication date, then the oldest". The first `classics` batch
swept in a children's picture book, two ELT readers, a 1965 short story, and
Rilke's 1929 *Letters to a Young Poet*. Seven rows had to be removed, leaving
93.

Descending does not have this problem: unknown dates land on the last page.
**Prefer `order=d` where the era allows it.**

### `find` locates elements that are in the DOM but not visible

Goodreads renders the Batch Edit panel and the shelf-rename input into the DOM
before they are shown. `find` returns a live `ref` for both, and `form_input`
against that ref reports success — while changing nothing the user can see and
submitting nothing.

This bit twice: once renaming a shelf, once on the last `dystopia` add.
**A successful `form_input` is not evidence the control was reachable.**
Screenshot to confirm visibility before acting, and re-screenshot after.

### The `Batch Edit` link toggles, and the first click after a navigate often misses

Sometimes the first click opens the panel; sometimes it does nothing and the
second opens it; a blind double-click opens then closes it. There is no
click-count that is reliably correct.

**Always screenshot between clicking `Batch Edit` and clicking `select all`.**
A blind `select all` on a page whose panel never opened silently does nothing —
which is indistinguishable from success until you check the counts.

### Element refs go stale across navigations

`ref_503` for the shelf dropdown is stable *within* a page but invalid after
`navigate`. Re-`find` it each time; a stale ref fails loudly, which is the good
case.

### Screenshots time out on 100-row pages

`Script injection timed out after 5000ms` shows up regularly while a bulk POST
is settling, and on tall table pages generally. `get_page_text` is much lighter
and usually succeeds where `screenshot` will not — use it for verification, and
reserve screenshots for the moments where pixel position actually matters.

### Author search over-matches

`search[query]` hits titles as well as authors. `poe` caught Dickinson's
*Selected Poems*, Frost's *Poems*, *Dead Poets Society*, and Sarah Kay;
`Orwell` returned a *Complete Works* omnibus alongside the novels. Read the
result titles before `select all`.

## Removing books, carefully

`remove books from this shelf` sits directly beside `remove books from all
shelves`. They are adjacent, similarly worded, and one of them is destructive.

**Click the remove control by element `ref`, not by coordinate.** Coordinates
drift with row height and text wrapping; the ref does not.

## Verify by reload, never by the optimistic UI

After `add books to this shelf` the link is replaced by a spinner and the
`shelves` column does *not* update in place. The sidebar count is stale too.
Reload `/shelf/edit` and read the number.

This also resolves the extension-disconnect case: if the connection drops
mid-POST, the write has usually still landed server-side. Reading the count on
the next page load tells you whether to retry — guessing does not.
