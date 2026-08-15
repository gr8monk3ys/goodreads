# Write-Flows: Captured Contracts (verified live)

> Captured 2026-06-19 against a real authenticated session (account user_id 168274083).
> This **supersedes** the assumptions in the design spec §6.6/§9: Goodreads writes in 2026
> do **not** use `/shelf/add_to_shelf.json` form-POSTs — they use an **AWS AppSync GraphQL**
> API with a short-lived JWT. Verified by performing a reversible add→remove (net-zero).

## Auth & transport

- **Endpoint:** `POST https://kxbwmqov6jgg3daaamb744ycu4.appsync-api.us-east-1.amazonaws.com/graphql`
  - The AppSync API id (`kxbwmqov6jgg3daaamb744ycu4`) may change — read it at runtime if it breaks. (TODO: confirm whether it's stable; for now treat as capture-time constant.)
- **Headers:** `content-type: application/json`, `authorization: <JWT>` (raw JWT, no `Bearer` prefix).
- **JWT:** RS256; claims include `iss=https://www.goodreads.com`, `user_id`, `role=user`, and **`exp` ~5 minutes after `iat`**. Sourced from the book page's `__NEXT_DATA__` → `props.pageProps.jwtToken`. **Refresh by reloading a page** — one page load powers a short batch of mutations, then re-fetch.
- **Apollo client:** `@apollo/client` v4.1.6 (sent in `extensions.clientLibrary`).
- **Stealth REQUIRED:** plain headless Chromium → **403 Forbidden** (AWS WAF). With `playwright-stealth` (`Stealth().use_sync(...)`) + realistic `user_agent`/`viewport`/`locale="en-US"`/`timezone_id` → works. The login-health check must detect 403 (title "403 Forbidden"), not just absence of "sign_in".

## Book identifier

- Mutations use the **GID**, not the numeric legacyId: `kca://book/amzn1.gr.book.v1.<base64ish>`.
- Available from `__NEXT_DATA__` apolloState `Book` entry's `id` field (the catalog parser already locates the Book entry; extend it to also return `id`). `legacyId` is the numeric id.

## Mutations (captured)

### ShelveBook (add / set shelf)  ✓ 200
```json
{"operationName":"ShelveBook",
 "variables":{"input":{"id":"kca://book/amzn1.gr.book.v1.<...>","shelfName":"to-read"}},
 "query":"mutation ShelveBook($input: ShelveBookInput!) { shelveBook(input: $input) { shelving { legacyId id shelf { name displayName editable default actionType sortOrder webUrl } webUrl taggings { tag { name } } } } }"}
```
- `shelfName` exclusive values seen in UI: `to-read`, `currently-reading`, `read` (also a "Did Not Finish" option). Assigning re-shelves (exclusive shelves auto-demote).
- Success signal: page metric `pageAction: add_to_wtr`, `Operation: ShelveBook, StatusCode: 200`.

### UnshelveBook (remove)  ✓ confirmed net-zero
```json
{"operationName":"UnshelveBook",
 "variables":{"input":{"id":"kca://book/amzn1.gr.book.v1.<...>"}}}
```
- Full query string not yet captured verbatim (only operationName + variables) — capture the exact selection set before relying on the response shape; the request shape above is confirmed sufficient to remove.

## UI selectors (fallback / driving the React app)

- Action container: `[data-testid="book-actions"]`.
- **Add to Want-to-Read (unshelved):** `button.Button--wtr.Button--block` (aria `"Tap to shelve book as want to read"`). Single click = one `ShelveBook` mutation, no modal.
- **Shelved-state button:** `button[aria-label^="Shelved as"]` (e.g. `"Shelved as 'Want to Read'. Tap to edit shelf for this book"`) — presence ⇒ shelved.
- **Remove flow (multi-step modal):** click shelved button → modal "Step 1 of 2: Choose a shelf" → check `button[aria-label="Tap to remove from my shelf"]` → click the **"Remove"** confirm button → fires `UnshelveBook`. (A plain click on the checkbox alone does nothing.)
- **Rating stars:** `button[aria-label="Rate N out of 5"]` inside `.BookRatingStars` (N=1..5). Buttons are duplicated for responsive layouts — act on the one with `offsetParent !== null`.
- Note: most controls render **twice** (desktop + mobile); always pick the visible instance.

## Classic Rails endpoints (captured 2026-08-14, live browser session)

The classic (non-React) pages still exist and use plain Rails endpoints — a much simpler
write surface than AppSync. Verified by really performing the writes (created the
`existential-classics` shelf and tagged 9 books with it; all visible on the profile after).

- **`GET /review/edit/<legacy_book_id>`** — stable authenticated editor page per book:
  rating stars, shelf/tag picker, dates-read, review textarea. Works for every book already
  on a shelf. This is the natural Playwright-fallback surface — no React modals.
  - Picker quirk: the "Choose shelves..." control needs the page's JS settled; a click
    before that focuses but doesn't open (retry once).
- **Custom shelf create:** `POST https://www.goodreads.com/user_shelves` → 200
  (form POST from `/shelf/edit`; shelf appears immediately). Fills the "custom shelf
  create" gap below at the endpoint level.
- **Custom-shelf tagging:** `POST https://www.goodreads.com/shelf/add_to_shelf` → 200
  (AJAX from the classic picker; fired once per tick, applies instantly — no Save/Post
  needed). Note: **not** `/shelf/add_to_shelf.json` as the design spec guessed.
- **Feature shelf on profile:** radio on `/shelf/edit` (AJAX per click; verified by the
  profile page rendering the featured shelf strip).
- Not recorded: exact request bodies/CSRF params (the capture tool logged method/URL/status
  only). Before implementing, capture one payload verbatim — the form fields are visible in
  the `/shelf/edit` and `/review/edit` page source.

## Still to capture
- **Rating** mutation (click a star) and its un-rate. (GraphQL `RateBook` since captured —
  see `actions/graphql.py`; the classic editor's star widget is an alternative surface.)
- **Review** create/update mutation + the editor flow (`reviewEditUrl` appears in the `myReviewCard` query). The classic `/review/edit/<id>` page's form is the likely simplest path.
- **Request bodies** for `/user_shelves` and `/shelf/add_to_shelf` (endpoints + methods confirmed above).
- **Listopia list add** mutation.

## Recommended backend approach
Hybrid, GraphQL-first: load the book page once (stealth) to get `jwtToken` + GID + current shelf state, then POST the GraphQL mutation(s) directly with that JWT. Fall back to driving the UI selectors above if a mutation contract changes. Keep the AppSync URL + mutation strings in one module so a change is a one-file fix.
