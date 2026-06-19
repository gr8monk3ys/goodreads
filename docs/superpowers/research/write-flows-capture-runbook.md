# Write-Flows Live-Capture Runbook

> **Why this exists:** Goodreads has no API, so every write goes through your logged-in browser session. The exact 2026 DOM selectors and request contracts **cannot be known without an authenticated session** — the research flagged all of them as "confirm live." This is the one step only you can do. It takes ~15–20 minutes, once. Afterward, fill in `src/gr_autopilot/actions/playwright_backend.py` and the suite can write for real.

## Prerequisites

```bash
uv sync --extra browser --extra voice --extra generate   # install Playwright + model + Claude
uv run playwright install chromium                       # download the browser
export ANTHROPIC_API_KEY=sk-ant-...                       # for generation
```

## Step 1 — Capture your session (one-time)

```bash
uv run python -c "from gr_autopilot.browser.session import login; login()"
```
A headed Chromium opens at the Goodreads sign-in page (Amazon login). Complete sign-in **including any MFA/CAPTCHA**, then click ▶ in the Playwright Inspector to resume. This writes `playwright/.auth/state.json` (gitignored). The cookie is short-lived (hours–weeks, not a year), so expect to re-run this periodically; the suite's login-health check will tell you when.

## Step 2 — Capture each write flow

Open a book you've read (one you want to review) while logged in, then record each action with DevTools → **Network** (preserve log) and the **Elements** inspector. For each item below, write down (a) the **CSS selector** of the control and (b) for any XHR/fetch, the **method + URL + request payload + headers** (especially `X-CSRF-Token`).

| # | Action | What to capture |
|---|--------|-----------------|
| 1 | **Set "Want to Read" / change shelf** | Click the shelf dropdown → pick a shelf. Capture the dropdown selector AND the request: confirm whether it's `POST /shelf/add_to_shelf.json` with body `book_id` / `name` / `v=2`. |
| 2 | **Post a review + star rating** | Hover/click the star widget (capture its selector), click "Write a review", type, Save. Capture the editor selector, Save-button selector, and the submit request (URL + payload). |
| 3 | **Create a custom shelf (tag)** | Open shelf management, add a shelf, note exclusive-vs-not. Capture the "Add shelf" control selector + the create request. |
| 4 | **Remove from a shelf** | Capture the remove control + request (historically `a=remove`). |
| 5 | **Add a book to a Listopia list** | Open a list → add a book. Capture the add control selector + request. |
| 6 | **`book_id` in markup** | Confirm where the numeric `book_id` appears on a 2026 book page (data attribute? URL?). |
| 7 | **CSRF token** | Confirm `<meta name="csrf-token">` is present and that write POSTs require it as `X-CSRF-Token`. |

## Step 3 — Record findings

Save your captures in a sibling file `write-flows-captured.md` (selectors + request contracts), then implement the four methods in `src/gr_autopilot/actions/playwright_backend.py` against them. Each method currently raises `NotImplementedError` with a hint.

## Step 4 — Validate safely

1. **Dry-run first** — never write blind:
   ```bash
   uv run gr ingest goodreads_library_export.csv
   uv run gr voice build           # (added in a later plan; or build the index in pipeline)
   uv run gr review --dry-run --limit 1
   ```
   Inspect `actions_log` (status `dry_run`) and the generated draft.
2. **One real write** — flip to live for a single low-stakes action:
   ```bash
   uv run gr review --no-dry-run --limit 1
   ```
   Verify on Goodreads, then check `actions_log` shows `done`.
3. **Kill switch** — confirm `uv run gr stop` (writes `data/STOP`) halts an in-flight run, and that `GR_DISABLE_WRITES=1` blocks writes.

## Safety reminders (autonomous mode)

- Keep `GR_MAX_ACTIONS_PER_RUN` conservative (default 10) and the throttle delays human-like.
- Writes are scrutinized far more than reads; ramp volume slowly and watch for any account warnings.
- The account is your **Amazon** account — suspension risk is real even though mitigated. The kill switch + dry-run are your safety net.
- The self-hosted runner that performs writes must stay on a **private** repo.
