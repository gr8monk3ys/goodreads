# goodreads-autopilot — Design Spec

> Status: **Approved (sign-off 2026-06-18)** · Date: 2026-06-18 · Companion: [verified research notes](../research/2026-06-18-goodreads-autopilot-research.md)
>
> A production Python suite that automates a single Goodreads account: ingests the user's library, learns their reviewing voice into a vector DB, generates new reviews with Claude, and writes back to Goodreads (reviews, ratings, shelves/tags, want-to-read, lists) via an authenticated browser session — because **no Goodreads API exists**. Runs fully autonomously with a kill switch and dry-run underneath, and ships with CI that both schedules the automation and gates code quality before merge.

---

## 1. Problem & Goals

Goodreads retired its API (no keys since 2020-12-08; existing keys 403 by late 2025). The user wants to automate their account anyway: write reviews in their own style, manage shelves/tags, add books to want-to-read, and create Listopia lists — without doing it by hand.

**Goals**
1. **Ingest** the user's full library from the official CSV export into a normalized local store.
2. **Learn voice**: embed existing reviews into a vector DB for style-conditioned retrieval (RAG).
3. **Generate** new reviews in the user's voice with Claude, grounded in retrieved exemplars.
4. **Write back** to Goodreads autonomously via Playwright: post reviews + ratings, shelve (incl. want-to-read), manage custom shelves (tags), create/append Listopia lists.
5. **Operate safely**: dry-run, kill switch, throttling, idempotency, login-health checks.
6. **CI/CD**: (a) a PR quality gate that blocks merge on lint/type/test/security failures; (b) a scheduled automation pipeline whose write jobs run on a residential self-hosted runner.

**Success = ** a `gr` CLI + scheduled CI that, given a fresh CSV export and a captured session, generates and posts on-voice reviews for read-but-unreviewed books and applies shelf/tag/list changes, with every action idempotent, throttled, dry-runnable, and killable — and a green-required PR gate.

## 2. Non-Goals & Constraints

- **No official API.** All writes go through the authenticated React UI (primary) or captured JSON endpoints (secondary). This is the only ToS-risky surface and is quarantined behind one adapter.
- **Account-risk is real and accepted.** Goodreads ToS permits termination "for any reason" and runs human+automated bot enforcement; the account is tied to the user's **Amazon** account. The user chose *fully autonomous* writes; the suite mitigates with conservative throttling, dry-run, and a kill switch — it cannot eliminate the risk.
- **No multi-account / SaaS.** Single-user, single-account, local-first.
- **No live scraping of the catalog** in v1 (the user's own data comes from CSV). A read-scrape path is allowed only where a `book_id` or DOM fact must be fetched to perform a write.

## 3. Operating Decisions (locked) + Defaults for Open Questions

**Locked by the user:** fully autonomous writes (kill switch + dry-run underneath) · review corpus from Goodreads CSV export · Claude API generation · Python + GitHub Actions (write jobs on a self-hosted residential runner). Stack defaults from verified research: **uv** + **Playwright** + **Chroma** + **sentence-transformers (bge-small-en-v1.5)**, saved **storage_state** auth, **GPL-3.0** (repo already is).

**Defaults chosen for the 8 open product questions** (override at review):

| # | Question | Default |
|---|----------|---------|
| 1 | Generation-target scope | `Exclusive Shelf == 'read'` **AND** empty review **AND** `My Rating > 0` (rating>0 configurable, default ON). One review per `book_id`; re-reads (`Read Count > 1`) treated as one target. Custom exclusive shelves excluded by default. |
| 2 | Write-job autonomy gate | Fully autonomous on cron. Kill switch = `DISABLE_WRITES` env **and** a `STOP` sentinel file checked before every action. Optional GitHub **Environment approval** gate available but **OFF** by default. |
| 3 | Write surface scope | **Both Phase A + B in the first build** (sign-off): post review + set rating + set exclusive shelf (incl. want-to-read) **and** custom shelves (tags) + Listopia lists. Each action individually toggleable; build sequences A before B internally for incremental verification. |
| 4 | Account-risk posture | Accepted (user chose autonomous). Conservative throttle defaults: `MAX_ACTIONS_PER_RUN=10`, randomized 8–25s inter-action delay, daily cap, exponential backoff. |
| 5 | AI labeling / human-in-loop | No label, no human gate by default (autonomous). `LABEL_AI_REVIEWS` and `REQUIRE_APPROVAL` config flags available, default OFF. Dry-run + kill switch are the safety net. |
| 6 | CI coverage / security gating | `pytest --cov-fail-under=80` blocks. Ruff `S` rules (flake8-bandit) **block**; standalone Bandit emits **SARIF** to the Security tab (non-blocking) to avoid double-gating noise. |
| 7 | Self-hosted runner form factor | Ephemeral container/VM on a residential connection, dedicated **non-root** user, `harden-runner` egress allowlist. Must be online for cron ticks; missed ticks caught by next run (idempotent). |
| 8 | Repo privacy | **Confirmed already private** (sign-off). This is what makes the self-hosted residential runner safe; privacy must be *maintained* — a public repo + self-hosted runner = fork-PR RCE on the user's machine. |

## 4. Architecture

Layered Python package `gr_autopilot`. Each layer has one purpose, a typed interface, and is testable in isolation. The ToS-risky `browser`/`actions` layers are the only ones that touch Goodreads; everything above them is pure local data work.

```
gr_autopilot/
  config/        Settings (pydantic-settings): paths, model, safety limits, kill switch, feature flags
  ingest/        CSV export parser -> normalized records (csv.DictReader, header-name access)
  store/         SQLite repository: books, reviews, shelves, book_shelves, actions_log, runs
  voice/         Embedder + VectorStore protocols; SentenceTransformerEmbedder + ChromaStore; index build + retrieve
  generate/      Claude client: cached voice prefix + RAG exemplars -> on-voice review draft (+ batch path)
  browser/       Playwright session: storage_state load/save, stealth, pacing, login-health, CSRF read
  actions/       High-level account ops behind one adapter: post_review, set_rating, set_shelf, want_to_read,
                 ensure_shelf (tag), add_to_list  — each idempotent & dry-run-aware
  orchestrator/  Workflows: review_unreviewed(), sync_shelves(), backfill() — compose store+voice+generate+actions
  cli/           Typer app: gr login | ingest | voice build | review | run | status | stop
docs/ tests/ .github/workflows/
```

**Interfaces (the seams that keep layers swappable):**

```python
class Embedder(Protocol):
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    @property
    def dimension(self) -> int: ...

class VectorStore(Protocol):
    def upsert(self, ids: list[str], vectors: list[list[float]], metadata: list[dict]) -> None: ...
    def query(self, vector: list[float], k: int, where: dict | None = None) -> list["Exemplar"]: ...

class GoodreadsActions(Protocol):   # the ONLY ToS-risky surface
    def post_review(self, book_id: int, text: str, rating: int, *, dry_run: bool) -> "ActionResult": ...
    def set_shelf(self, book_id: int, shelf: str, *, dry_run: bool) -> "ActionResult": ...
    def ensure_shelf(self, name: str, *, exclusive: bool, dry_run: bool) -> "ActionResult": ...
    def add_to_list(self, list_id: str, book_id: int, *, dry_run: bool) -> "ActionResult": ...
```

**End-to-end data flow:** CSV export → `ingest` → SQLite → `voice` embeds reviews → for each target book, retrieve top-k stylistically similar past reviews → `generate` (Claude + cached voice prefix + exemplars) → draft → `actions` (via `browser`) posts review / sets shelf / tags / lists → `store.actions_log` records the action (idempotency) → `runs` records the run summary.

## 5. Data Model (SQLite)

`book_id` (Goodreads integer) is the primary key everywhere — **never ISBN** (e-books have empty ISBNs).

- **books**(book_id PK, title, author, author_lf, additional_authors, isbn, isbn13, my_rating, avg_rating, publisher, binding, num_pages, year_published, orig_year, date_read, date_added, exclusive_shelf, read_count, owned_copies)
- **reviews**(review_id PK, book_id FK, review_html, review_text, has_spoiler, is_empty GENERATED, source ENUM[csv|generated], generated_at)
- **shelves**(shelf_id PK, name, is_exclusive)
- **book_shelves**(book_id FK, shelf_id FK, position) — many-to-many
- **actions_log**(id PK, run_id FK, book_id, action_type, payload_hash, status ENUM[planned|dry_run|done|failed|skipped_idempotent], dry_run, created_at, detail) — **idempotency key** = (book_id, action_type, payload_hash)
- **runs**(run_id PK, started_at, finished_at, mode ENUM[dry_run|live], actions_planned, actions_done, actions_failed, notes)

Listopia list membership has **no dedicated table in v1** — `add_to_list` idempotency uses `actions_log` (action_type=`add_to_list`, payload_hash=`list_id`); list/shelf names ride in action payloads while `book_id` remains the catalog PK.

`is_empty` is a STORED generated column over normalized `review_text` so target detection is a pure query.

## 6. Subsystem Specs

Each subsystem is built TDD-first. "AC" = acceptance criteria (the tests that must pass).

### 6.1 `ingest` — CSV → records
- **Input:** `goodreads_library_export.csv` (fixed 31-column header).
- **Logic:** `csv.DictReader(encoding='utf-8', newline='')`; read by header name. `clean_isbn()` strips the `="..."` spreadsheet-formula wrapper → `None` if empty. `norm_review()` converts `<br/>` → `\n`, strips tags, unescapes entities, trims. Dates parsed `YYYY/MM/DD`.
- **AC:** parses the verified 31-column header; `="160486530X"` → `160486530X`, `=""` → `None`; a `<br/>`-only review normalizes to `''` and is flagged empty; a multi-line `<br/>`-joined review round-trips to text with newlines; Book Id used as PK; missing trailing columns (older exports) don't crash (header-name access).

### 6.2 `store` — SQLite repository
- **Logic:** idempotent upsert keyed on `book_id`; schema migrations; `targets()` query = `exclusive_shelf == 'read' AND reviews.is_empty == 1 [AND my_rating > 0]`. `actions_log` enforces idempotency via the (book_id, action_type, payload_hash) key.
- **AC:** re-ingesting the same CSV produces no duplicate rows; `targets()` returns only read-and-unreviewed (and, by default, rated) books; recording the same action twice is a no-op flagged `skipped_idempotent`.

### 6.3 `voice` — embeddings + retrieval
- **Logic:** `SentenceTransformerEmbedder('BAAI/bge-small-en-v1.5', normalize_embeddings=True)`; the BGE query instruction is applied **queries-only** in `embed_query`. `ChromaStore` via `chromadb.PersistentClient(path=...)`, **version-pinned**, embeddings passed explicitly (not the built-in EF, so the query instruction is honored). One review = one chunk; metadata = {rating, shelves}. **The Goodreads CSV has no genre field**, so "genre" filtering uses a shelf-derived proxy (user shelves like `fantasy`/`sci-fi`, drawn from `book_shelves`) when present. Retrieve k=5 (configurable 4–8), pre-filter by rating band (and the shelf-genre proxy when available), de-dup exemplars at cosine > 0.95.
- **AC:** building the index over N reviews yields N vectors of `dimension`; a query returns k exemplars ordered by similarity; metadata `where` filter restricts results; the persist dir is reloadable; the index **cache key includes model name + dimension** (model swap forces re-embed). Embedder is swappable to a `VoyageEmbedder` stub with no call-site change.

### 6.4 `generate` — Claude review drafting
- **Logic:** request = **(A)** frozen, **prompt-cached** system prefix: distilled voice guidelines + retrieved exemplars (sorted, byte-stable) + a short "avoid AI tells" block with `cache_control:{"type":"ephemeral"}` on the last block; **(B)** per-book metadata as the uncached final user turn. Default model `claude-sonnet-4-6` (knob up to `claude-opus-4-8`, down to `claude-haiku-4-5`). `thinking:{"type":"adaptive"}`; **no** `prefill`/`budget_tokens`/`temperature` (rejected by Opus 4.8). Word count steered by prompt + post-validation; generous `max_tokens≈2000`. Bulk backfills use the **Batches API** (50% discount, caching stacks).
- **AC:** a generated draft is non-empty and within the requested word band (post-validated); `usage.cache_read_input_tokens > 0` on the second call with the same prefix (cache hit asserted in an integration test, mockable in unit tests); model knob switches the request without other changes; an optional `humanizer` post-pass runs when enabled.

### 6.5 `browser` — Playwright session layer
- **Logic:** two entrypoints — interactive **`login`** (`headless=False`, `page.pause()` so the human clears Amazon MFA/CAPTCHA) → `context.storage_state(path='playwright/.auth/state.json', indexed_db=True)`; recurring headless **`run`** that loads storage_state. `playwright-stealth` v2.x `Stealth()` context manager + consistent UA/viewport/locale/timezone; `navigator.webdriver`→`undefined`. **Login-health check** every run (GET an auth-required page, assert sign-out/username present) → fail loudly on expiry. CSRF token read from `meta[name="csrf-token"]` per fresh page load. Re-save storage_state after successful runs. `playwright/.auth/` is gitignored.
- **AC:** storage_state saved by `login` authenticates a headless context (integration, manual creds); login-health check returns False on an injected-expired cookie; stealth init script sets `navigator.webdriver === undefined`; no secret is ever written to a tracked path.

### 6.6 `actions` — account write operations (the quarantined surface)
- **Logic:** each op drives the **real React UI** as primary path (clicks star widget / Want-to-Read / shelf dropdown / review editor / Save), with the captured JSON endpoint (`/shelf/add_to_shelf.json` + `X-CSRF-Token`) as a secondary fast path **only after the live contract is captured** (see §9). Every op: checks kill switch → checks idempotency → applies throttle/jitter → executes (or logs in dry-run) → records to `actions_log`.
- **AC:** in `dry_run`, no network write occurs and an action is logged `dry_run`; kill switch (`DISABLE_WRITES` or `STOP` file) aborts before any write; a repeat action is `skipped_idempotent`; selectors live in one mapping module so a DOM change is a one-file fix. (Live write ACs are smoke tests gated behind a real session + opt-in flag.)

### 6.7 `orchestrator` + `cli`
- **Workflows:** `review_unreviewed()` (targets → generate → post), `sync_shelves()`, `backfill()` (Batches). **CLI (Typer):** `gr login`, `gr ingest <csv>`, `gr voice build`, `gr review [--dry-run] [--limit N] [--model ...]`, `gr run` (full pipeline), `gr status`, `gr stop` (writes the `STOP` sentinel).
- **AC:** `gr review --dry-run` runs end-to-end with zero writes and a run summary; `gr stop` halts an in-flight run before the next action; `--limit` caps actions.

## 7. Safety & Account-Risk Controls (active even in autonomous mode)

Kill switch (`DISABLE_WRITES` env + `STOP` sentinel file, checked before *every* action) · global `--dry-run` · per-run `MAX_ACTIONS` cap + daily cap · randomized human-like 8–25s inter-action delays · exponential backoff + jitter on errors · idempotency log (no double-posts on re-run) · login-health assertion before any write · all actions logged *before* execution · conservative defaults shipped on.

**Partial-failure behavior:** a failed action is logged `failed` and the run continues to the next target (one bad book never aborts the batch); `runs.actions_failed` aggregates them and `gr status` surfaces the failures for inspection.

## 8. CI/CD Topology

Three artifacts:
1. **`.github/workflows/ci.yml`** — PR gate. Triggers `pull_request:[main]` **and** `push:[main]` (required checks only register after running on default branch). Named parallel jobs `lint` (ruff), `typecheck` (mypy --strict), `test` (pytest --cov-fail-under=80), `security` (bandit→SARIF). `astral-sh/setup-uv@v8` + `uv sync --locked`; tools via `uv run`.
2. **`.github/workflows/automation.yml`** — `schedule: cron` + `workflow_dispatch`, `concurrency` serializes runs. **Two-stage by design:** a **generate** job on `ubuntu-latest` (contacts `api.anthropic.com` only, never Goodreads) produces drafts and uploads the SQLite store as an artifact; a dependent **post** job on `runs-on: [self-hosted, linux, x64, residential, playwright]` downloads it and performs the Playwright writes (contacts `www.goodreads.com` only). This keeps `ANTHROPIC_API_KEY` off the home machine and shrinks the residential runner's egress to Goodreads alone. Each job is wrapped with `step-security/harden-runner` (generate allowlist: anthropic + github; post allowlist: goodreads + github) and `timeout-minutes`. On the persistent self-hosted runner, `storage_state` lives on the machine directly; the `PLAYWRIGHT_STORAGE_STATE_B64` secret (decoded to a tempfile, scrubbed in `if: always()`) is the hosted-runner fallback. `ANTHROPIC_API_KEY` is job-scoped to `generate`.
3. **Branch-protection ruleset** — created via `gh api --method POST /repos/OWNER/REPO/rulesets --input ruleset.json` (the `-F` flag encoding 422s). Requires the four named checks green before merge.

## 9. Live-Discovery Procedure (resolves the must-confirm-live list)

The write internals can't be known without an authenticated session, so implementation of §6.6 **begins** with a capture step, documented and committed to `docs/superpowers/research/write-flows-captured.md`:
1. `gr login` to obtain a real session.
2. With Playwright `page.on('request')`/DevTools, perform each action **manually once** and record: method, full URL, body params, headers (incl. `X-CSRF-Token`), and the stable CSS selectors for the star widget, Write-a-Review button, editor, Save, shelf dropdown, Add-shelf control, remove-from-shelf, and Listopia add.
3. Confirm: `/shelf/add_to_shelf.json` 2026 param contract; review-post endpoint/payload; how `book_id` appears in 2026 markup; logged-in `_session_id2` lifetime (sets re-login cadence).
4. Encode findings in the single selectors/endpoints mapping module; write smoke tests.

Until captured, `actions` ships UI-driven with selectors marked provisional; `--dry-run` and unit tests don't depend on live capture.

## 10. Build Order & Milestones

Dependency order, each its own spec→plan→build→review cycle where useful:
1. **Foundation**: repo scaffold (uv, pyproject, ruff/mypy/pytest/bandit config), `config`, `ci.yml`, branch-protection ruleset. *(Get the quality gate green on an empty package first.)*
2. **ingest + store** — CSV → SQLite, target detection. *(First real subsystem.)*
3. **voice** — embeddings + Chroma retrieval.
4. **generate** — Claude RAG drafting (mockable; cache-hit asserted).
5. **browser + live capture (§9) + actions** — the ToS-risky layer, dry-run-first. With A+B in scope, `actions` covers reviews/ratings/shelves **and** custom-shelf (tag) + Listopia-list ops; §9 capture includes the create-shelf and list-add flows.
6. **orchestrator + cli** — wire it together.
7. **automation.yml** + self-hosted residential runner (private repo) — scheduled writes.

## 11. Overall Acceptance Criteria

`gr ingest` → `gr voice build` → `gr review --dry-run` runs the full pipeline on the user's real CSV with zero writes and a coherent run summary; generated drafts read in the user's voice (spot-checked) and pass the AI-tells check; flipping off dry-run posts to Goodreads with throttling + idempotency + kill switch demonstrably working; the PR gate is green and required; the scheduled write job runs on the private-repo residential runner.

## 12. Open Questions for User Sign-Off

**Resolved at sign-off (2026-06-18):** (1) rated-reads-only targets; (2) **both** Phase A + B in the first build; (3) unlabeled & unattended — dry-run + kill switch are the only gate; (4) repo already private; (5) coverage 80% + Bandit non-blocking accepted. Original questions retained for the record:
1. Generation targets: rated-reads-only (default) vs all read-but-unreviewed?
2. Write surface: ship Phase A only first (reviews+ratings+shelves), or A+B together (also tags+lists)?
3. Keep AI reviews unlabeled and unattended (default), or label / add a one-time approval gate?
4. Confirm the GitHub repo will be **private** before a residential runner is attached (hard requirement).
5. Coverage gate at 80% and Bandit non-blocking — acceptable?

## 13. Risks

Account suspension (autonomous writes vs ToS; account = Amazon account) — mitigated, not eliminated. storage_state is a live credential (base64 ≠ encryption). Cron is best-effort and disabled after ~60 days repo inactivity. Selectors/endpoints rot (React rewrite) — isolated to one module + smoke tests. Embeddings capture topic > authorial voice — acceptable for a single-author corpus, controlled via metadata filtering.
