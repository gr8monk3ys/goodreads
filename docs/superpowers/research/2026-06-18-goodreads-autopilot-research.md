# goodreads-autopilot — Technical Research Notes

> Status: verified research synthesis (2026-06-18). Findings below were produced by area-specific research and then adversarially verified; verdicts are reflected inline. Claims marked **CONFIRM LIVE** could not be verified without an authenticated session and MUST be checked during implementation. This document grounds the spec and implementation plan.
>
> **Project frame:** `goodreads-autopilot` automates a single Goodreads account fully autonomously (with a kill switch + dry-run underneath). No usable Goodreads API exists; all writes go through an authenticated Playwright session. Review corpus comes from the Goodreads CSV export. Generation uses the Claude API. Runtime is Python + GitHub Actions, with write jobs on a self-hosted/residential runner. RAG uses Chroma + local sentence-transformers. Auth uses a saved Playwright `storage_state`.

---

## 1. CSV Export Schema & Ingest

### Verified facts
The Goodreads "Export Library" CSV (`goodreads_library_export.csv`) has a **fixed 31-column header**, confirmed byte-for-byte against a real raw export ([raw export gist](https://gist.githubusercontent.com/tmcw/f077b2f174a0194f62b94bec4e88f4d0/raw)) and cross-checked against a parser's source ([GRAnalysis utils/book.py](https://raw.githubusercontent.com/JohnSmithDev/GRAnalysis/master/utils/book.py)).

Exact header order (all 31, confirmed):
`Book Id, Title, Author, Author l-f, Additional Authors, ISBN, ISBN13, My Rating, Average Rating, Publisher, Binding, Number of Pages, Year Published, Original Publication Year, Date Read, Date Added, Bookshelves, Bookshelves with positions, Exclusive Shelf, My Review, Spoiler, Private Notes, Read Count, Recommended For, Recommended By, Owned Copies, Original Purchase Date, Original Purchase Location, Condition, Condition Description, BCID`

Key quirks (all **confirmed**):
- **ISBN/ISBN13 are spreadsheet-formula strings.** Raw cell is `"=""160486530X"""`; after CSV unquoting the Python value is `=\"160486530X\"`. Strip with regex `=\"(.*)\"`. Empty ISBN unquotes to `=\"\"`. Use **Book Id** as primary key, never ISBN (e-books have empty ISBNs).
- **Exclusive Shelf is the canonical reading status** — exactly one of `read` / `currently-reading` / `to-read`, OR a user-created custom exclusive shelf. It is NOT a strict three-value enum (users can create custom exclusive shelves — [confirmed via Goodreads help](https://help.goodreads.com/s/article/How-do-I-create-custom-shelves-1553870934223)). Filter targets on `== 'read'`.
- **My Review is HTML.** Line breaks are encoded as `<br/>` tags, not literal newlines — confirmed independently by a [Goodreads-to-markdown script](https://gist.github.com/finmoorhouse/4fd8ddb50a6b9a7d9690f049992f89c9) that does `row['My Review'].replace("<br/>", "\n")`. Empty review = empty string.
- **Empty-review detection must normalize first:** strip HTML tags (`<br/>`, `<br>`, `<p>`), decode `&nbsp;`, trim whitespace; if the result is empty the review is absent. A naive `if row['My Review']:` is INSUFFICIENT (a `<br/>`-only cell is semantically empty).
- **Dates** (`Date Read`, `Date Added`) are `YYYY/MM/DD`, empty when unset.
- **Bookshelves** is `', '`-separated; **Bookshelves with positions** annotates each with `(#n)` ordinals.
- **My Rating** 0–5 (0 = unrated); **Average Rating** is a decimal community average; **Read Count**/**Owned Copies** are integers.

### Generation-target rule (load-bearing, confirmed/derived)
A book is a **READ-but-UNREVIEWED generation target** when `Exclusive Shelf == 'read'` AND `normalize(My Review) == ''`. Optionally add `My Rating > 0` to restrict to rated reads (product decision — see open questions).

### Recommended approach
- Parse with **stdlib `csv.DictReader`** (`encoding='utf-8', newline=''`), NOT pandas — pandas coerces Book Id/ISBN digits to floats and blanks to NaN. Read columns by **header name**, never positional index, to survive column drift.
- Store in a normalized **SQLite** schema: `books`, `reviews`, `shelves`, `book_shelves`. Store both raw review HTML (`review_html`) and normalized plain text (`review_text`), with a generated `is_empty` column.

```python
import csv, re, html
from datetime import datetime

ISBN_RE = re.compile(r'=\"(.*)\"')
BR_RE   = re.compile(r'<br\s*/?>', re.I)
TAG_RE  = re.compile(r'<[^>]+>')

def clean_isbn(s):
    s = s or ''
    m = ISBN_RE.match(s)
    return ((m.group(1) if m else s).strip()) or None

def norm_review(s):
    t = BR_RE.sub('\n', s or '')
    t = TAG_RE.sub('', t)
    return html.unescape(t).strip()

# target = read but unreviewed
# is_read = row['Exclusive Shelf'] == 'read'
# if is_read and not norm_review(row['My Review']): ...
```

```sql
CREATE TABLE reviews (
  review_id INTEGER PRIMARY KEY,
  book_id   INTEGER NOT NULL REFERENCES books(book_id),
  review_html TEXT,   -- raw My Review with <br/>
  review_text TEXT,   -- normalized plain text
  has_spoiler INTEGER DEFAULT 0,
  is_empty INTEGER GENERATED ALWAYS AS
      (CASE WHEN review_text IS NULL OR review_text='' THEN 1 ELSE 0 END) STORED
);
```

### Risks
- The `<br/>` HTML assumption is confirmed in general but the user's specific reviews may be single-line plain text — validate against their real export.
- Older exports may trim trailing columns (Condition, BCID) — header-name access mitigates.
- Custom exclusive shelves break the three-value enum assumption.

---

## 2. Write Flows (authenticated browser automation)

### Verified facts
- **No API.** The Goodreads developer API stopped issuing keys **2020-12-08** and is effectively dead ([Slashdot 2020-12-17](https://developers.slashdot.org/story/20/12/17/1522242/goodreads-is-retiring-its-current-api-and-book-loving-developers-arent-happy)). Legacy OAuth XML endpoints (`/review.xml`, `/shelf/add_to_shelf.xml`, `user_shelves.create`) require keys no longer issued — **reference-only** for param naming ([Drupal node/1463932](https://www.drupal.org/node/1463932)).
- **Infra is AWS CloudFront, NOT Cloudflare/DataDome** (confirmed via live response headers: `via ...cloudfront.net`, `x-amz-cf-id`, `x-amz-cf-pop`). TLS/JA3 fingerprint tricks are likely unnecessary for an authenticated cookie-bearing session.
- **Auth cookie is `_session_id2`** (HttpOnly), alongside `ccsid` (long-lived, expires 2046) and `locale`. Injecting a valid `_session_id2` authenticates a context.
  - **⚠ Refuted sub-claim:** the "~1yr expiry" is wrong. Observed unauthenticated `_session_id2` lifetime is **~6 hours**; community reports for logged-in cookies are "several weeks." `ccsid` is the long-lived cookie. **Plan for frequent re-capture/refresh of `storage_state`, not annual.**
- **CSRF token** is exposed as `<meta name="csrf-token" content="...">` on pages (confirmed live). Write POSTs need it as the `X-CSRF-Token` header. The token is per-session/per-page — re-read from a fresh page load.
- **Login moved to Amazon** (`amazon.com/ap/signin`, OpenID, `siteState`). The 2020-era native Rails form fields (`user[email]`, `user[password]`, hidden `n`) are **gone** (confirmed — zero matches live). Do not script the Amazon login blind; it adds MFA/CAPTCHA/device-trust friction.
- **`POST /shelf/add_to_shelf.json` still exists** in 2026 (returns HTTP 302→`/user/new` unauthenticated, not 404 — confirmed live). Body `book_id`/`name`/`v=2`, header `X-CSRF-Token`, from [DobleV55/Goodreads add_book.py](https://raw.githubusercontent.com/DobleV55/Goodreads/master/goodreads/add_book.py) (2020). **Endpoint reachability is confirmed; the exact 2026 param/response contract is NOT — CONFIRM LIVE.**
- **Exclusive shelf semantics** (confirmed): assigning `read`/`currently-reading`/`to-read` auto-demotes the other exclusive shelves; custom non-exclusive shelves coexist ([Goodreads blog 1399](https://www.goodreads.com/blog/show/1399-custom-bookshelves)).
- **ToS risk is real** (confirmed): Goodreads ToS permits termination "for any reason"; it runs combined human+automated review and suspends bot accounts ([Goodreads ToS](https://www.goodreads.com/about/terms)). The at-risk unit is the **account**, which may also be the user's Amazon account.

### Recommended approach
1. **Auth once, reuse.** Run Playwright headed once; let a human complete the Amazon sign-in (+MFA/CAPTCHA); call `context.storage_state(path=...)`. Re-use for all runs. (Cookie-injection of `_session_id2` is the alternative but cookies expire fast.)
2. **Prefer driving the real React UI** (click star widget, Want-to-Read/shelf dropdown, review editor, Save) over replaying raw endpoints — the UI carries CSRF/headers automatically and is more resilient to the 2022 React rewrite. Replay raw endpoints only after capturing the live contract.
3. **For every write**, read the CSRF token from `meta[name="csrf-token"]` on a fresh authenticated page load.
4. **Login health check** every run: after loading `storage_state`, GET an auth-required page and assert the username/sign-out link is present before issuing writes, so an expired session fails loudly instead of silently 302-ing writes to login.
5. **Throttle and humanize writes aggressively.** This is the main risk lever (CloudFront is lax on reads but writes are scrutinized).

```python
token = page.eval_on_selector('meta[name="csrf-token"]', 'el => el.content')
# POST /shelf/add_to_shelf.json  headers {X-CSRF-Token: token}
# data {book_id, name: 'to-read'|'read'|'currently-reading'|<custom>, v: '2'}
# ⚠ CONFIRM the 2026 contract via authenticated DevTools/Playwright network capture first.
```

### Risks / must-confirm
Most selectors/endpoints predate the React rewrite. The hardest part is login automation (Amazon MFA/CAPTCHA). See **must_confirm_live** for the full list of selectors/endpoints to capture from a real authenticated session.

---

## 3. Playwright Auth, Stealth & Pacing

### Verified facts (all confirmed against official Playwright docs)
- **`context.storage_state(path='state.json')`** saves cookies + localStorage (+ IndexedDB with `indexed_db=True`, added v1.51); **`browser.new_context(storage_state='state.json')`** reuses it. Passing no path returns a dict ([BrowserContext API](https://playwright.dev/python/docs/api/class-browsercontext)).
- Official guidance: store auth state in **`playwright/.auth/`** and **`.gitignore` it** ([auth guide](https://playwright.dev/python/docs/auth)).
- State is **portable headed→headless** (plain JSON, no mode metadata). Headed run only exists so a human can clear 2FA/CAPTCHA; `page.pause()` (Inspector, headed-only) or `input()` holds it open.
- **`playwright codegen <url> --save-storage=auth.json`** bootstraps state interactively ([codegen docs](https://playwright.dev/python/docs/codegen)).
- **sessionStorage is NOT persisted** by `storage_state`; if a site uses it, serialize via `page.evaluate()` and restore via `context.add_init_script()`.
- **playwright-stealth v2.x** uses `from playwright_stealth import Stealth; with Stealth().use_sync(sync_playwright()) as p:` — the v1.x `stealth_sync`/`stealth_async` functions are legacy. (Latest is **v2.0.3**, Apr 4 2026, per [PyPI](https://pypi.org/project/playwright-stealth/) — minor correction to the cited v2.0.2.)
- **`navigator.webdriver` should be masked to `undefined`, not `false`** (detectors flag the boolean `false` as a patch).
- **Stealth covers only JS-level signals** and cannot defeat TLS/JA3-JA4, CDP timing, or ML behavioral detection. Against Cloudflare Enterprise/DataDome/Akamai/PerimeterX it fails. (The specific "7–12 of 40+ checks" ratio is **illustrative, not verified** — treat directionally.)
- **Expired-session detection**: check `page.url` for sign-in routes and/or `page.on('response', ...)` for 401/403; simulate expiry by injecting a cookie with a past `expires` via `context.add_cookies`.

### Recommended approach for goodreads-autopilot
- Two entrypoints: a one-time interactive **`login`** (`headless=False`) and recurring headless **`run`**.
- Because Goodreads is **CloudFront, not Cloudflare**, do NOT invest in defeating fingerprinting. Rely on a **real reused session + light stealth + human pacing**. Apply `Stealth()` plus a realistic, internally-consistent `user_agent`/`viewport`/`locale`/`timezone_id` (a mismatched IP/locale is itself a signal).
- Wrap fragile actions in exponential backoff + jitter (`base * 2**attempt * uniform(0.5,1.5)`, 3–5 retries) and enforce a per-run `MAX_ACTIONS` cap.
- Re-save `storage_state` at the end of successful runs to capture rotated cookies and extend longevity.

```python
context.add_init_script("""
  Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
  Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
""")
```

### Risks
storage_state expires (plan periodic re-login); base64 secrets are obfuscation not encryption; partial/incorrect spoofing (e.g. `webdriver=false`) is more detectable than none.

---

## 4. Voice RAG (style-conditioned retrieval)

### Verified facts
- **Default embedder: `BAAI/bge-small-en-v1.5`** — 384-dim, 33.4M params, 512 max seq, MTEB 62.17 / STS 81.59, MIT, ~133MB fp32 ([model card](https://huggingface.co/BAAI/bge-small-en-v1.5)). Use `normalize_embeddings=True`. The query instruction (`"Represent this sentence for searching relevant passages:"`) is **OPTIONAL for v1.5** (only slight retrieval degradation without it), queries-only, never on passages.
- `thenlper/gte-small` (384-dim, MIT, **no prefix needed**, symmetric encoding) is a near-equal drop-in if the BGE prefix bookkeeping is undesirable.
- `all-MiniLM-L6-v2` (384-dim, **256-token cap**, MTEB ~56) is a baseline only — ~6-point quality gap.
- Step-ups (768-dim): `bge-base-en-v1.5` (~63.5 MTEB) and `nomic-embed-text-v1.5` (8192-token context, Matryoshka dims **512/256/128/64**, needs task prefixes + `trust_remote_code=True` on current stacks). Only if reviews are long or bge-small underperforms.
- **Vector store: Chroma** (decided per project constraints). `chromadb.PersistentClient(path=...)` persists to a **self-contained SQLite directory** (`chroma.sqlite3` + per-collection HNSW index files — **DuckDB was removed in Chroma 0.4.0**; the cited "DuckDB/SQLite" was outdated). Ships `SentenceTransformerEmbeddingFunction`, `get_or_create_collection`, `where={...}` metadata filtering. The directory is fully cacheable. **Pin the chromadb version and include it in the cache key** — the on-disk format has changed across releases.
  - ⚠ Caveat: Chroma's built-in embedding function applies the same function to docs and queries, so it can't apply BGE's query-only instruction. For strict BGE correctness, **embed manually and pass `embeddings=...`** rather than relying on the built-in EF.
- **Exemplar count k≈5 (sweep 4–8)** for voice/style conditioning, supported by [few-shot style research](https://arxiv.org/html/2509.14543v1); semantically-similar exemplar selection is functionally RAG.
- **Future swap to Voyage** maps `embed_documents`→`input_type='document'`, `embed_query`→`input_type='query'`. ⚠ Correction: **`voyage-3.5` is fixed at 1024-dim** (no `output_dimension`). Use `voyage-3.5-lite`/`voyage-3-large`/voyage-4 family for selectable dims.

### Recommended approach
- One review = one chunk (avoid over-chunking; style lives in the whole review). Store `rating`, `shelf`, `genre` as metadata.
- Retrieve k=5 by similarity to the target book, **pre-filtering by genre/rating band** so exemplars match context; de-duplicate near-identical exemplars (cosine > ~0.95).
- Abstract behind two Protocols (`Embedder` with `embed_documents`/`embed_query`/`dimension`; `VectorStore`) so the local→Voyage swap is a one-class change. Bake **model name + dimension** into the index cache key — a model swap forces a full re-embed.
- Build the index in a deterministic offline step; cache the persist directory in GitHub Actions keyed on `hashFiles(corpus + embedding.py + pyproject)`, and cache `~/.cache/huggingface` separately on model name.

### Risks
General embeddings capture **topic more than authorial voice** — for a single-author corpus that's acceptable (the author IS the voice); use metadata filtering to control topic. Small corpora (hundreds–thousands) should use **flat/brute-force search**, not ANN (IVF_PQ hurts recall at small scale).

---

## 5. Claude Generation

### Verified facts (against live platform.claude.com docs)
- **Pricing/MTok:** Opus 4.8 $5/$25; Sonnet 4.6 $3/$15; Haiku 4.5 $1/$5. Cache write = 1.25× (5m) / 2× (1h); cache read = 0.1× (~90% savings) ([models overview](https://platform.claude.com/docs/en/about-claude/models/overview), [prompt caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching)).
- **Documented default is Opus 4.8** ("if unsure, start with Opus 4.8"). Sonnet 4.6 is the recommended **balanced** tier for cost-sensitive high-volume creative work — present this as a tradeoff, not a silent downgrade.
- **Prompt caching is prefix-match**; render order tools→system→messages. Put the stable voice prefix + exemplars first (cached); put per-book target in the final user turn after the last breakpoint. Min cacheable prefix: **Opus 4.8 / Sonnet 4.6 = 1,024 tokens** (the cached skill's 4,096 for Opus was wrong); Haiku 4.5 = 4,096. Max 4 breakpoints; default TTL 5m, 1h via `ttl:"1h"`.
- Verify hits via `usage.cache_read_input_tokens` / `cache_creation_input_tokens` / `input_tokens`.
- **Voice cloning = 3–8 real exemplars as few-shot** (heuristic count, not a documented figure). Earlier-turn assistant few-shot messages are allowed.
- **2026 model gotchas (confirmed):**
  - **No assistant-turn prefill** on Sonnet 4.6 / Opus 4.8 / Fable 5 (400). Use `output_config.format` or system instruction instead.
  - **No `budget_tokens`** on Opus 4.8/4.7 (400); use `thinking:{"type":"adaptive"}`.
  - **No `temperature`/`top_p`/`top_k`** on Opus 4.8/4.7 (400) — steer style via prompt; on Sonnet 4.6 they work, pass at most one of temperature/top_p.
- **Structured outputs** via `output_config.format` (json_schema) or `client.messages.parse()` with Pydantic → `response.parsed_output`. Limits: no recursive schemas, **no numeric/length constraints** (enforce word count via prompt + post-validation), `additionalProperties:false` required. Changing the schema **invalidates the cache** and injects a hidden format system prompt — freeze it.
  - ⚠ The "incompatible with citations (400)" claim is **unverified** against the canonical doc; prefill-incompatibility is moot since prefill is already blocked.
- **Length control:** no word↔token param — instruct word count in prompt + generous `max_tokens`. Max output: Opus 4.8 128k, Sonnet 4.6 / Haiku 4.5 64k (Haiku's 200k is context, not output).
- **Batches API:** up to 100k requests, **50% discount**, prompt caching stacks, most finish <1h ([overview](https://platform.claude.com/docs/en/about-claude/models/overview)).
- **Anti-AI-tells:** the [`anthropic-skills:humanizer`](#) skill (Wikipedia "Signs of AI writing") is the canonical pattern list (em-dash overuse, "not just X but Y", rule-of-three, inflated adjectives, vague attributions, hollow -ing tails). Lead with real exemplars; on Opus 4.7+ a short anti-slop nudge suffices.
- On Opus 4.8/Sonnet 4.6, prefer **plain declarative guidance + positive exemplars** over long negative "do not" lists (models follow instructions literally).

### Recommended approach
Structure each request as (A) a **frozen, cached** system prompt = distilled voice guidelines + the user's retrieved exemplars + a short "avoid AI tells" block (with `cache_control:{"type":"ephemeral"}` on the last block); (B) per-book metadata as the **uncached final user turn**. Use `thinking:{"type":"adaptive"}`, generous `max_tokens` (~2000), and an explicit word-count instruction. Keep the prefix byte-stable (sort exemplars; no timestamps/uuids; `json.dumps(sort_keys=True)`); assert `cache_read_input_tokens > 0`. Use the **Batches API** for shelf backfills; synchronous calls for interactive generation.

### Risks
Silent cache misses balloon cost ~12× on the prefix. Voice mimicry/authenticity: this is the user's own account and own corpus (fully autonomous by decision), so consent is satisfied — but a dry-run + kill switch underneath is the safety net.

---

## 6. CI/CD (GitHub Actions, uv, self-hosted residential runner)

### Verified facts
- **Three workflows**, not one: `ci.yml` (PR gate), `automation.yml` (scheduled writes), branch protection as a **ruleset**.
- **`astral-sh/setup-uv@v8`** (v8.2.0, Jun 2026) with `enable-cache: true` (true/false/auto) + `cache-dependency-glob`; install via **`uv sync --locked --all-extras --dev`** (`--locked` fails on lockfile drift); run tools via `uv run` ([uv GH integration](https://docs.astral.sh/uv/guides/integration/github/), [setup-uv](https://github.com/astral-sh/setup-uv)).
- **Bandit 1.9.3** (Jan 2026) reads `[tool.bandit]` from pyproject (needs `bandit[toml]`), emits SARIF via `bandit[sarif]` ([Bandit](https://github.com/PyCQA/bandit)).
- **Required-check registration:** checks only appear in the ruleset picker after running on the **default branch** — add a `push: [main]` trigger alongside `pull_request` ([community #167194](https://github.com/orgs/community/discussions/167194)). The check identifier is the **job name**, so name each gate (`lint`, `typecheck`, `test`, `security`).
- **Self-hosted runners must NEVER be on public repos** (fork-PR RCE / secret exfiltration). Use private repo, `--ephemeral`, dedicated non-root user, network segmentation ([GitHub secure-use](https://docs.github.com/en/actions/reference/security/secure-use)).
- **Runner routing** via labels (AND semantics): `runs-on: [self-hosted, linux, x64, residential, playwright]`. The `residential` label routes WRITE traffic through the residential IP. (Labels are case-insensitive.)
- **`step-security/harden-runner@v2`** for egress audit/block + allowlist on self-hosted runners.
- **Playwright browsers installed at runtime** (`uv run playwright install --with-deps chromium`); caching binaries is discouraged ([Playwright CI](https://playwright.dev/python/docs/ci)). On the long-lived self-hosted runner you can pre-install on the host.
- **storage_state as a base64 GitHub secret**, decoded to a file at job start (community pattern, not an official Playwright feature; GitHub secrets do support multi-line values, so base64 is optional but avoids escaping pitfalls).
- **Rulesets** are the modern branch-protection replacement. ⚠ **Refuted:** the `gh api -F 'rules[][parameters]...'` flag encoding **fails with 422** — pass a JSON file via `--input` instead ([community #139808](https://github.com/orgs/community/discussions/139808)). The JSON field names (`required_status_checks[].context`, `strict_required_status_checks_policy`, `required_approving_review_count`) are correct ([REST rules](https://docs.github.com/en/rest/repos/rules)).

### Recommended approach
- `ci.yml`: parallel named jobs (lint/typecheck/test/security) on `ubuntu-latest`, triggered on `pull_request: [main]` AND `push: [main]`. Pin actions to major tags (full SHA for security-sensitive jobs). Least-privilege `permissions:`.
- `automation.yml`: `schedule: cron` + `workflow_dispatch`, `concurrency` to serialize runs. Read-only jobs on hosted runners; the **WRITE job on the self-hosted residential runner**, wrapped with harden-runner (audit→block: `api.anthropic.com`, github endpoints, `www.goodreads.com`), `timeout-minutes`, optional `environment: production` for manual approval (relevant given the autonomous-but-kill-switch design).
- Decode storage_state from `PLAYWRIGHT_STORAGE_STATE_B64`; scrub the file in an `if: always()` step. Pass `ANTHROPIC_API_KEY` via `env:` scoped to jobs that need it.
- Configure the ruleset via `gh api --method POST /repos/OWNER/REPO/rulesets --input ruleset.json`.

### Risks
Public-repo self-hosted runner = critical RCE vector (keep private). storage_state is a live credential (base64 ≠ encryption). Cron is best-effort and disabled after ~60 days of repo inactivity. Residential IP reduces datacenter flagging but does not authorize the activity (ToS).

---

## 7. Prior Art (adopt vs build)

### Verified landscape
- **No usable API** → all read tooling is HTML scraping; **no write API at all**.
- **Ingest is well-served.** [`YashTotale/goodreads-user-scraper`](https://github.com/YashTotale/goodreads-user-scraper) (Python, MIT, **freshest**, pushed 2026-06-17, cookie auth, retry/backoff/resume, pipx/uvx) is the best base — but it is **READ-ONLY**. [`havanagrawal/GoodreadsScraper`](https://github.com/havanagrawal/GoodreadsScraper) (Scrapy+Selenium, MIT, 146★) is best for bulk metadata patterns.
  - **Do NOT adopt:** `maria-antoniak/goodreads-scraper` (GPL, 305★, README says "no longer functioning"); `rixx/goodreads-to-sqlite` (depends on dead legacy API); `andre-st/goodreads-toolbox` (Perl, archived).
- **Write layer has no mature upstream.** The one instructive write reference is [`gmoran1016/Hardcover-Sync`](https://github.com/gmoran1016/Hardcover-Sync) (Python, no license, 0★, pushed 2026-04): it documents the only working modern recipe — **headless Chrome + Selenium + SAVED COOKIES (not form login)** because "Goodreads uses Amazon's login infrastructure which blocks headless browsers with a CAPTCHA." Treat as **documentation, not a dependency** (unlicensed, unproven).
- **License:** our repo is **GPL-3.0**, empty (README + LICENSE only — confirmed locally). MIT upstreams can be incorporated freely; GPL upstreams are compatible.

### Recommendation
- **Ingest:** for this project we already export from the **CSV** (not scrape), so goodreads-user-scraper is a secondary asset — adopt its **cookie-capture + retry/backoff/resume patterns**, not its scraping core. Borrow havanagrawal's Scrapy structure only if catalog-scale metadata is later needed.
- **Write/browser layer: BUILD.** No adoptable codebase. Replicate the proven **Playwright + saved storage_state** architecture (we use Playwright over Selenium for better auto-waiting/stealth). Standardize on **one storage_state** powering both any reads and all writes.
- Isolate all write logic behind a thin adapter; keep the write surface minimal (add-to-shelf, mark-as-read, rate, review); add smoke tests asserting the flows still work.

---

## MUST CONFIRM AT IMPLEMENTATION TIME

These could not be verified without an authenticated session and MUST be captured live (DevTools / Playwright `page.on('request')`) before coding against them:

1. The exact 2026 request (method, URL, body, headers) for **changing an exclusive shelf** / "Want to Read" — verify whether `/shelf/add_to_shelf.json` still takes `book_id`/`name`/`v=2`.
2. The endpoint + payload for **posting a text review + star rating** from the React review editor (legacy `review[rating]`/`review[review]` is OAuth-only).
3. **CSS selectors / DOM paths** for the star-rating widget, "Write a Review" button, review text editor, Save button, and shelf dropdown on the post-2022 React book page.
4. The endpoint/form for **removing a book from a shelf** (historically `a=remove`).
5. The endpoint/params to **create a custom shelf** and mark exclusive vs non-exclusive; the "Add shelf" control selector.
6. Whether the **Amazon `ap/signin` flow** can be driven unattended at all (MFA/CAPTCHA) for this account, or whether interactive cookie capture is the only path.
7. **`_session_id2` validity duration** for a logged-in session and whether it is bound to IP/User-Agent (affects headless reuse / re-login cadence).
8. The real **write-rate threshold** that flags the account vs the lax read-scraping posture.
9. Whether the book page **exposes `book_id`** easily in 2026 markup for programmatic shelving.
10. **Model availability/pricing/min-cache thresholds** for `claude-opus-4-8` / `claude-sonnet-4-6` / `claude-haiku-4-5` — re-verify against platform.claude.com before shipping.
11. The user's **actual CSV**: full 31-column set present? Reviews multi-line `<br/>` or single-line plain text?
12. `harden-runner` exact input names (`allowed-endpoints`, `use-policy-store`) against docs.stepsecurity.io.


---

## 8. Locked Technical Decisions

### Vector store

- **Decision:** Chroma (chromadb) via PersistentClient, version-pinned
- **Rationale:** Per operating decision. Confirmed self-contained SQLite + HNSW directory (NOT DuckDB — removed in 0.4.0), fully CI-cacheable. Pin the chromadb version and include it in the actions/cache key because the on-disk format has changed across releases. Embed manually and pass embeddings=... rather than the built-in embedding function, so BGE's query-only instruction can be applied correctly.

### Embedding model

- **Decision:** BAAI/bge-small-en-v1.5 (384-dim) via local sentence-transformers, normalize_embeddings=True
- **Rationale:** Best size/quality point for short reviews (MTEB 62.17, ~133MB, MIT, fully offline). Query instruction is OPTIONAL for v1.5 but applied queries-only via embed_query(). thenlper/gte-small is the no-prefix fallback. Bake model name + dimension into the index cache key so a model swap forces a re-embed.

### Embedder/store abstraction

- **Decision:** Two Protocols — Embedder (embed_documents/embed_query/dimension) and VectorStore — with SentenceTransformerEmbedder now and a VoyageEmbedder stub
- **Rationale:** Voyage's document/query input_type asymmetry mirrors BGE's instruction prefix, so the local→Voyage swap is a one-class change with no call-site edits. Note: voyage-3.5 is fixed at 1024-dim; use voyage-3.5-lite/voyage-3-large/voyage-4 if selectable dims are needed later.

### Generation model (default)

- **Decision:** claude-sonnet-4-6 as the high-volume default; expose a model knob up to claude-opus-4-8 and down to claude-haiku-4-5
- **Rationale:** Sonnet 4.6 ($3/$15) is the documented balanced tier for cost-sensitive high-volume creative work. The documented/skill default is Opus 4.8, so surface the tradeoff rather than silently downgrading. Haiku 4.5 for bulk drafts.

### Generation architecture

- **Decision:** Cached frozen voice prefix (guidelines + retrieved exemplars + anti-AI-tells block, cache_control ephemeral on last block) + per-book metadata in uncached final user turn; thinking adaptive; no prefill; no budget_tokens; no temperature/top_p on Opus
- **Rationale:** Prefix-match prompt caching gives ~90% savings on the voice prefix paid once. 2026 models reject prefill/budget_tokens/sampling params (400). adaptive thinking aids voice matching. Assert cache_read_input_tokens>0 to catch silent invalidators.

### Bulk generation

- **Decision:** Use the Batches API (50% discount, prompt caching stacks) for shelf backfills; synchronous calls only for interactive generation
- **Rationale:** Confirmed up to 100k requests, most finish <1h. The shared voice prefix is cached across the batch.

### Anti-AI-tells

- **Decision:** Encode a short 'Signs of AI writing' prohibition block in the voice prompt and optionally run the anthropic-skills:humanizer skill as a post-pass; lead with real exemplars
- **Rationale:** Real exemplars suppress AI tells better than rule lists; on Opus 4.7+ a short nudge suffices. Avoid long negative 'do not' lists which over-trigger literal-following models.

### CSV ingest

- **Decision:** Parse with stdlib csv.DictReader (utf-8, newline=''); normalize into SQLite (books/reviews/shelves/book_shelves); store raw review_html + normalized review_text
- **Rationale:** Avoids pandas dtype coercion of Book Id/ISBN to floats. Header-name access survives column drift. Generated is_empty column drives target detection.

### Generation-target detection

- **Decision:** Exclusive Shelf == 'read' AND normalize(My Review) == '' (HTML/<br/>/&nbsp;-stripped). My Rating > 0 left as a configurable filter
- **Rationale:** Exclusive Shelf is the confirmed canonical reading status; naive truthiness on My Review is insufficient because <br/>-only cells are semantically empty.

### Primary key

- **Decision:** Goodreads Book Id (integer) as the primary key across the suite, never ISBN
- **Rationale:** Confirmed many rows (e-books) have empty ISBN/ISBN13; Book Id is stable and always present.

### Auth strategy

- **Decision:** One-time interactive headed Playwright login through Amazon (human clears MFA/CAPTCHA) → context.storage_state(path='playwright/.auth/state.json', indexed_db=True); reuse headless. Re-save at end of successful runs. Add a login-health check that fails loudly on expiry
- **Rationale:** Amazon ap/signin can't be driven blind; the 2020 native Rails form is gone. Cookie-injection of _session_id2 is the fallback but observed lifetime is short (~hours unauth, ~weeks logged-in), so plan frequent storage_state refresh — NOT the assumed ~1yr.

### Write mechanism

- **Decision:** Drive the real React UI with Playwright as the primary write path; treat /shelf/add_to_shelf.json + X-CSRF-Token as a secondary fast path only after capturing the live 2026 contract
- **Rationale:** UI path carries CSRF/headers automatically and resists the React rewrite; the raw endpoint's 2026 param shape is unconfirmed (only reachability/302 is confirmed).

### Stealth posture

- **Decision:** playwright-stealth v2.x Stealth() context manager + realistic consistent UA/viewport/locale/timezone + human pacing; do NOT invest in TLS/fingerprint evasion
- **Rationale:** Goodreads is behind AWS CloudFront (confirmed), not Cloudflare/DataDome, so an authenticated reused session + light stealth suffices. Mask navigator.webdriver to undefined (not false).

### Package manager / tooling

- **Decision:** uv (astral-sh/setup-uv@v8) with uv.lock; ruff (lint+format), mypy --strict, pytest+coverage, bandit; all via uv run
- **Rationale:** Per operating decision. uv sync --locked fails CI on lockfile drift. Bandit reads [tool.bandit] and emits SARIF.

### CI/CD topology

- **Decision:** Three workflows: ci.yml (PR gate, hosted, named jobs, push+pull_request triggers), automation.yml (cron writes, read jobs hosted + WRITE job on self-hosted residential runner), branch protection as a ruleset via gh api --input JSON
- **Rationale:** Confirmed: required checks only register after running on the default branch (hence push:[main]); the gh api -F flag encoding for rulesets fails with 422 (use --input JSON file); self-hosted runners must be private-repo-only + ephemeral + non-root.

### Secrets handling

- **Decision:** storage_state as base64 GitHub secret decoded to a tempfile at job start and scrubbed in if:always(); ANTHROPIC_API_KEY via env scoped to needing jobs; WRITE job optionally gated behind an Environment with required reviewers
- **Rationale:** storage_state is a live credential (base64 is obfuscation, not encryption). The Environment gate fits the kill-switch/dry-run design.

### Safety underlayer

- **Decision:** Build dry-run mode + kill switch beneath all writes; aggressive write throttling with jitter and a per-run MAX_ACTIONS cap; login-health assertion before any write
- **Rationale:** Account suspension risk is real (ToS termination for any reason; human+automated bot enforcement). The account is also the user's Amazon account. Writes are scrutinized more than reads despite lax read posture.

### Browser engine

- **Decision:** Playwright (Python), not Selenium
- **Rationale:** Per operating decision; better auto-waiting and stealth in 2026 than the Selenium-based prior-art references, while replicating their proven saved-cookie architecture.

### License

- **Decision:** Keep the suite GPL-3.0
- **Rationale:** Repo is already GPL-3.0 and empty; MIT upstreams (patterns from goodreads-user-scraper, havanagrawal) are freely incorporable, GPL upstreams compatible.

---

## 9. Adopt vs Build

- **YashTotale/goodreads-user-scraper (Python, MIT, github.com/YashTotale/goodreads-user-scraper)** — Adopt patterns, not the core (we ingest from CSV, not scrape): the cookie-capture/session approach, retry-with-exponential-backoff, resumable non-zero-exit behavior, and pipx/uvx packaging ergonomics. Useful as a reference if any live read-scraping (e.g. fetching a book_id from a book page) becomes necessary.

- **gmoran1016/Hardcover-Sync (Python, no license, github.com/gmoran1016/Hardcover-Sync)** — Treat as DOCUMENTATION not a dependency (unlicensed, 0 stars, unproven). Replicate its load-bearing architecture decision: authenticate via SAVED BROWSER COOKIES captured in a one-time interactive (headful) login, NOT form login, because Goodreads' Amazon login CAPTCHA-blocks headless browsers. Re-implement in Playwright with storage_state.

- **havanagrawal/GoodreadsScraper (Python, Scrapy+Selenium, MIT, github.com/havanagrawal/GoodreadsScraper)** — Borrow the Scrapy spider + item-pipeline structure ONLY IF catalog-scale book/author/review metadata (beyond the user's own CSV library) is later required. Not needed for the core CSV-driven flow.

- **DobleV55/Goodreads (Python, MIT, github.com/DobleV55/Goodreads)** — Reference-only for the /shelf/add_to_shelf.json write recipe (book_id/name/v=2, X-CSRF-Token header). Its login half is broken (2020 native Rails form, now Amazon-mediated). Use solely as a starting hypothesis for the live network-capture confirmation.

---

## 10. Open Product Questions (resolved as defaults in the spec; user may override)

- Generation-target scope: include read-but-UNRATED books, or only rated reads (My Rating > 0)? How to treat re-reads (Read Count > 1) and books on custom exclusive shelves?
- WRITE-job autonomy gate: fully autonomous on the cron schedule, or gated behind a GitHub Environment with required reviewers / manual approval per run? (Operating decision is 'fully autonomous with kill switch + dry-run underneath' — confirm whether the manual-approval Environment is part of the kill switch or bypassed.)
- Write surface scope: which exact actions does autopilot perform — post text review, set star rating, mark-as-read, add-to-shelf, custom shelves, reading-progress, Listopia? Breakage surface and ToS risk scale with scope; minimal scope is strongly recommended.
- Acceptable account-risk posture: automating writes against the user's real Goodreads (= Amazon) account may violate ToS and risk suspension of an account tied to purchases. Confirm the user accepts this and the conservative throttling defaults.
- Should AI-generated reviews be labeled as AI-assisted, and is any human review-before-publish desired despite the 'fully autonomous' decision (vs. relying solely on dry-run + kill switch)?
- Coverage threshold for the CI test gate (e.g. --cov-fail-under=85) and whether Bandit findings hard-block merges or only report SARIF to the Security tab while ruff's S-rules act as the blocking gate.
- Self-hosted runner form factor: bare-metal residential box vs container/VM on a residential connection (changes the ephemeral/isolation approach), and whether it stays online 24/7 to catch every cron tick (plus a fallback if offline when the schedule fires).
- Is the target repo private? The entire self-hosted-residential-runner design is only safe on a private repo — must be confirmed before wiring a residential machine to it.
