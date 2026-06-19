# goodreads-autopilot — Plan 01: Foundation + Ingest + Store

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the `gr_autopilot` Python package with a green CI quality gate, and deliver the first real feature — parse the Goodreads CSV export into a normalized SQLite store and detect read-but-unreviewed review targets.

**Architecture:** `src/`-layout package managed by `uv`. `ingest` parses the export with stdlib `csv` (header-name access, never positional). `store` is a thin repository over stdlib `sqlite3` with a `schema.sql`. `config` is pydantic-settings. `cli` is a Typer app. Everything here is pure local data work — no network, no Goodreads, fully unit-testable.

**Tech Stack:** Python 3.12, uv, pydantic-settings, Typer, stdlib csv/sqlite3/re/html; dev: pytest + pytest-cov, ruff, mypy (strict), bandit. CI: GitHub Actions + astral-sh/setup-uv.

**Spec:** [2026-06-18-goodreads-autopilot-design.md](../specs/2026-06-18-goodreads-autopilot-design.md) §6.1, §6.2, §5, §8. **Covers spec sign-off:** rated-reads-only targets (`require_rating` default True).

---

## File Structure

```
pyproject.toml                          # project + tool config (ruff/mypy/pytest/bandit)
.gitignore                              # python, data/, playwright/.auth/, .env
.python-version                         # 3.12
src/gr_autopilot/__init__.py
src/gr_autopilot/config.py              # Settings (pydantic-settings)
src/gr_autopilot/ingest/__init__.py
src/gr_autopilot/ingest/csv_parser.py   # clean_isbn, norm_review, BookRecord, parse_export
src/gr_autopilot/store/__init__.py
src/gr_autopilot/store/schema.sql       # books, reviews, shelves, book_shelves
src/gr_autopilot/store/db.py            # connect(), init_db()
src/gr_autopilot/store/repository.py    # upsert_books(), targets()
src/gr_autopilot/cli.py                 # Typer app: ingest, status
tests/conftest.py                       # in-memory db fixture
tests/test_csv_parser.py
tests/test_repository.py
tests/fixtures/sample_export.csv        # real 31-col header + 3 rows
.github/workflows/ci.yml                # lint / typecheck / test / security
```

**Decisions locked here (YAGNI vs spec §5):** `reviews` is keyed by `book_id` (one review per book in v1) rather than a separate `review_id` — the target rule is one-review-per-book, so the surrogate key is unnecessary now. `actions_log`/`runs` tables are deferred to the actions plan (Plan 05) where they're first used.

---

## Task 0: Repo scaffold + uv

**Files:** Create `pyproject.toml`, `.gitignore`, `.python-version`, `src/gr_autopilot/__init__.py`

- [ ] **Step 1: Create `.python-version`**

```
3.12
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[project]
name = "gr-autopilot"
version = "0.1.0"
description = "Autonomous automation suite for a Goodreads account"
requires-python = ">=3.12"
dependencies = [
    "pydantic>=2.7",
    "pydantic-settings>=2.3",
    "typer>=0.12",
]

[project.scripts]
gr = "gr_autopilot.cli:app"

[dependency-groups]
dev = [
    "pytest>=8.2",
    "pytest-cov>=5.0",
    "ruff>=0.6",
    "mypy>=1.11",
    "bandit[toml,sarif]>=1.9",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/gr_autopilot"]

[tool.ruff]
line-length = 100
src = ["src", "tests"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "S"]
# S101 = assert-used: allowed in tests
[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101"]

[tool.mypy]
python_version = "3.12"
strict = true
files = ["src", "tests"]

[tool.pytest.ini_options]
addopts = "--cov=gr_autopilot --cov-report=term-missing --cov-fail-under=80"
testpaths = ["tests"]
pythonpath = ["src"]

[tool.bandit]
exclude_dirs = ["tests"]
```

- [ ] **Step 3: Create `.gitignore`**

```
__pycache__/
*.py[cod]
.venv/
.pytest_cache/
.mypy_cache/
.ruff_cache/
.coverage
htmlcov/
dist/
build/
*.egg-info/
data/
*.db
.env
playwright/.auth/
*storage_state*.json
```

- [ ] **Step 4: Create `src/gr_autopilot/__init__.py`**

```python
"""goodreads-autopilot: autonomous automation for a Goodreads account."""

__version__ = "0.1.0"
```

- [ ] **Step 5: Sync and verify the toolchain**

Run: `uv sync` then `uv run python -c "import gr_autopilot; print(gr_autopilot.__version__)"`
Expected: prints `0.1.0` (uv resolves deps, creates `.venv` and `uv.lock`).

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml .gitignore .python-version src/gr_autopilot/__init__.py uv.lock
git commit -m "chore: scaffold gr_autopilot package with uv toolchain"
```

---

## Task 1: Config (pydantic-settings)

**Files:** Create `src/gr_autopilot/config.py`, `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_config.py
from pathlib import Path

from gr_autopilot.config import Settings


def test_defaults():
    s = Settings()
    assert s.db_path == Path("data/autopilot.db")
    assert s.require_rating is True
    assert s.disable_writes is False
    assert s.model == "claude-sonnet-4-6"


def test_env_override(monkeypatch):
    monkeypatch.setenv("GR_REQUIRE_RATING", "false")
    monkeypatch.setenv("GR_MAX_ACTIONS_PER_RUN", "3")
    s = Settings()
    assert s.require_rating is False
    assert s.max_actions_per_run == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: gr_autopilot.config`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/gr_autopilot/config.py
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration. All keys are overridable via GR_* env vars."""

    model_config = SettingsConfigDict(env_prefix="GR_", env_file=".env", extra="ignore")

    db_path: Path = Path("data/autopilot.db")
    require_rating: bool = True          # rated-reads-only target rule (sign-off)
    disable_writes: bool = False         # kill switch (used by actions layer)
    max_actions_per_run: int = 10
    model: str = "claude-sonnet-4-6"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_config.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gr_autopilot/config.py tests/test_config.py
git commit -m "feat(config): pydantic-settings with GR_* env overrides"
```

---

## Task 2: CSV field helpers — `clean_isbn`, `norm_review`

**Files:** Create `src/gr_autopilot/ingest/__init__.py`, `src/gr_autopilot/ingest/csv_parser.py`, `tests/test_csv_parser.py`

- [ ] **Step 1: Write the failing test** (covers the verified CSV quirks)

```python
# tests/test_csv_parser.py
from gr_autopilot.ingest.csv_parser import clean_isbn, norm_review


def test_clean_isbn_strips_formula_wrapper():
    assert clean_isbn('="160486530X"') == "160486530X"


def test_clean_isbn_empty_wrapper_is_none():
    assert clean_isbn('=""') is None
    assert clean_isbn("") is None
    assert clean_isbn(None) is None


def test_clean_isbn_plain_value_passes_through():
    assert clean_isbn("9780441478125") == "9780441478125"


def test_norm_review_converts_br_to_newline_and_strips_tags():
    raw = "Line one.<br/>Line two.<br />Line three."
    assert norm_review(raw) == "Line one.\nLine two.\nLine three."


def test_norm_review_br_only_is_empty():
    assert norm_review("<br/>") == ""
    assert norm_review("") == ""
    assert norm_review(None) == ""


def test_norm_review_unescapes_entities():
    assert norm_review("Tom &amp; Jerry &nbsp;rule") == "Tom & Jerry  rule".strip()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_csv_parser.py -v`
Expected: FAIL — `ModuleNotFoundError: gr_autopilot.ingest.csv_parser`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/gr_autopilot/ingest/__init__.py
```
(empty file)

```python
# src/gr_autopilot/ingest/csv_parser.py
from __future__ import annotations

import html
import re

_ISBN_RE = re.compile(r'^="?(.*?)"?$')   # matches the ="..." spreadsheet-formula wrapper
_BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")


def clean_isbn(raw: str | None) -> str | None:
    """Strip Goodreads' ="..." spreadsheet-formula ISBN wrapper; '' -> None."""
    s = (raw or "").strip()
    m = _ISBN_RE.match(s)
    value = (m.group(1) if m else s).strip()
    return value or None


def norm_review(raw: str | None) -> str:
    """Normalize a 'My Review' HTML cell to plain text. <br/> -> newline; tags stripped."""
    text = _BR_RE.sub("\n", raw or "")
    text = _TAG_RE.sub("", text)
    return html.unescape(text).strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_csv_parser.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add src/gr_autopilot/ingest/ tests/test_csv_parser.py
git commit -m "feat(ingest): isbn + review field normalization helpers"
```

---

## Task 3: Parse the export into `BookRecord`s

**Files:** Modify `src/gr_autopilot/ingest/csv_parser.py`; Create `tests/fixtures/sample_export.csv`; Modify `tests/test_csv_parser.py`

- [ ] **Step 1: Create the fixture CSV** (real 31-column header, 3 rows)

```csv
# tests/fixtures/sample_export.csv
Book Id,Title,Author,Author l-f,Additional Authors,ISBN,ISBN13,My Rating,Average Rating,Publisher,Binding,Number of Pages,Year Published,Original Publication Year,Date Read,Date Added,Bookshelves,Bookshelves with positions,Exclusive Shelf,My Review,Spoiler,Private Notes,Read Count,Recommended For,Recommended By,Owned Copies,Original Purchase Date,Original Purchase Location,Condition,Condition Description,BCID
11,Dune,Frank Herbert,"Herbert, Frank",,"=""0441478123""","=""9780441478125""",5,4.25,Ace,Paperback,412,1990,1965,2024/03/01,2024/02/01,"sci-fi, favorites","sci-fi (#1), favorites (#2)",read,"Loved it.<br/>A masterpiece.",false,,1,,,1,,,,,
22,Some Skim,Jane Doe,"Doe, Jane",,"=""""","=""""",4,3.10,SelfPub,ebook,200,2020,2020,2024/05/01,2024/04/01,fantasy,fantasy (#3),read,,false,,1,,,0,,,,,
33,On The Pile,John Roe,"Roe, John",,"=""1111111111""","=""9781111111111""",0,3.90,Pub,Hardcover,300,2019,2019,,2024/06/01,to-read,to-read (#4),to-read,,false,,0,,,0,,,,,
```

(Row 11 = read + reviewed; row 22 = read + rated + **empty review** → a target; row 33 = to-read.)

- [ ] **Step 2: Write the failing test**

```python
# append to tests/test_csv_parser.py
from pathlib import Path

from gr_autopilot.ingest.csv_parser import parse_export

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def test_parse_export_reads_all_rows():
    records = parse_export(FIXTURE)
    assert len(records) == 3


def test_parse_export_fields_and_quirks():
    by_id = {r.book_id: r for r in parse_export(FIXTURE)}
    dune = by_id[11]
    assert dune.title == "Dune"
    assert dune.isbn == "0441478123"           # formula wrapper stripped
    assert dune.my_rating == 5
    assert dune.exclusive_shelf == "read"
    assert dune.review_text == "Loved it.\nA masterpiece."
    assert dune.shelves == ("sci-fi", "favorites")

    skim = by_id[22]
    assert skim.isbn is None                    # ="" -> None
    assert skim.review_text == ""               # empty review
    assert skim.exclusive_shelf == "read"
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_csv_parser.py -k parse_export -v`
Expected: FAIL — `ImportError: cannot import name 'parse_export'`.

- [ ] **Step 4: Write minimal implementation** (append to `csv_parser.py`)

```python
# add to top imports of csv_parser.py
import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BookRecord:
    book_id: int
    title: str
    author: str
    isbn: str | None
    isbn13: str | None
    my_rating: int
    avg_rating: float | None
    exclusive_shelf: str
    date_read: str | None
    date_added: str | None
    review_html: str
    review_text: str
    has_spoiler: bool
    shelves: tuple[str, ...]


def _row_to_record(row: dict[str, str]) -> BookRecord:
    review_html = row.get("My Review") or ""
    shelves = tuple(
        s.strip() for s in (row.get("Bookshelves") or "").split(",") if s.strip()
    )
    avg = row.get("Average Rating") or ""
    return BookRecord(
        book_id=int(row["Book Id"]),
        title=(row.get("Title") or "").strip(),
        author=(row.get("Author") or "").strip(),
        isbn=clean_isbn(row.get("ISBN")),
        isbn13=clean_isbn(row.get("ISBN13")),
        my_rating=int(row.get("My Rating") or 0),
        avg_rating=float(avg) if avg else None,
        exclusive_shelf=(row.get("Exclusive Shelf") or "").strip(),
        date_read=((row.get("Date Read") or "").strip() or None),
        date_added=((row.get("Date Added") or "").strip() or None),
        review_html=review_html,
        review_text=norm_review(review_html),
        has_spoiler=(row.get("Spoiler") or "").strip().lower() == "true",
        shelves=shelves,
    )


def parse_export(path: Path) -> list[BookRecord]:
    """Parse a goodreads_library_export.csv into BookRecords (header-name access)."""
    with open(path, encoding="utf-8", newline="") as f:
        return [_row_to_record(row) for row in csv.DictReader(f)]
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_csv_parser.py -v`
Expected: PASS (all parser tests).

- [ ] **Step 6: Commit**

```bash
git add src/gr_autopilot/ingest/csv_parser.py tests/test_csv_parser.py tests/fixtures/sample_export.csv
git commit -m "feat(ingest): parse export into BookRecords with verified quirks"
```

---

## Task 4: SQLite schema + db init

**Files:** Create `src/gr_autopilot/store/__init__.py`, `src/gr_autopilot/store/schema.sql`, `src/gr_autopilot/store/db.py`, `tests/conftest.py`, `tests/test_store.py`

- [ ] **Step 1: Create `src/gr_autopilot/store/schema.sql`**

```sql
CREATE TABLE IF NOT EXISTS books (
    book_id         INTEGER PRIMARY KEY,
    title           TEXT NOT NULL,
    author          TEXT,
    isbn            TEXT,
    isbn13          TEXT,
    my_rating       INTEGER DEFAULT 0,
    avg_rating      REAL,
    exclusive_shelf TEXT,
    date_read       TEXT,
    date_added      TEXT
);

CREATE TABLE IF NOT EXISTS reviews (
    book_id      INTEGER PRIMARY KEY REFERENCES books(book_id) ON DELETE CASCADE,
    review_html  TEXT,
    review_text  TEXT,
    has_spoiler  INTEGER DEFAULT 0,
    source       TEXT DEFAULT 'csv',
    generated_at TEXT,
    is_empty     INTEGER GENERATED ALWAYS AS
                 (CASE WHEN review_text IS NULL OR review_text = '' THEN 1 ELSE 0 END) STORED
);

CREATE TABLE IF NOT EXISTS shelves (
    shelf_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT UNIQUE NOT NULL,
    is_exclusive INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS book_shelves (
    book_id  INTEGER REFERENCES books(book_id) ON DELETE CASCADE,
    shelf_id INTEGER REFERENCES shelves(shelf_id) ON DELETE CASCADE,
    PRIMARY KEY (book_id, shelf_id)
);
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import sqlite3

import pytest

from gr_autopilot.store.db import init_db


@pytest.fixture
def conn() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    init_db(c)
    yield c
    c.close()
```

- [ ] **Step 3: Write the failing test**

```python
# tests/test_store.py
def test_init_db_creates_tables(conn):
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    ).fetchall()
    names = {r["name"] for r in rows}
    assert {"books", "reviews", "shelves", "book_shelves"} <= names


def test_is_empty_generated_column(conn):
    conn.execute("INSERT INTO books (book_id, title) VALUES (1, 'X')")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (1, '')")
    conn.execute("INSERT INTO books (book_id, title) VALUES (2, 'Y')")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (2, 'real')")
    empty = conn.execute("SELECT book_id FROM reviews WHERE is_empty = 1").fetchall()
    assert [r["book_id"] for r in empty] == [1]
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: gr_autopilot.store.db`.

- [ ] **Step 5: Write `src/gr_autopilot/store/__init__.py` (empty) and `db.py`**

```python
# src/gr_autopilot/store/db.py
import sqlite3
from pathlib import Path

_SCHEMA = Path(__file__).with_name("schema.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA.read_text(encoding="utf-8"))
    conn.commit()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add src/gr_autopilot/store/ tests/conftest.py tests/test_store.py
git commit -m "feat(store): sqlite schema + init with generated is_empty column"
```

---

## Task 5: Repository — `upsert_books` (idempotent)

**Files:** Create `src/gr_autopilot/store/repository.py`; Modify `tests/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_store.py
from pathlib import Path

from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.store.repository import upsert_books

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def test_upsert_is_idempotent(conn):
    records = parse_export(FIXTURE)
    upsert_books(conn, records)
    upsert_books(conn, records)  # second time must not duplicate
    assert conn.execute("SELECT COUNT(*) FROM books").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0] == 3
    # 'sci-fi','favorites','fantasy','to-read' = 4 distinct shelves
    assert conn.execute("SELECT COUNT(*) FROM shelves").fetchone()[0] == 4


def test_upsert_updates_review_text(conn):
    records = parse_export(FIXTURE)
    upsert_books(conn, records)
    row = conn.execute("SELECT review_text FROM reviews WHERE book_id = 11").fetchone()
    assert row["review_text"] == "Loved it.\nA masterpiece."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -k upsert -v`
Expected: FAIL — `ModuleNotFoundError: gr_autopilot.store.repository`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/gr_autopilot/store/repository.py
from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from gr_autopilot.ingest.csv_parser import BookRecord


def upsert_books(conn: sqlite3.Connection, records: Sequence[BookRecord]) -> int:
    for r in records:
        conn.execute(
            """
            INSERT INTO books (book_id, title, author, isbn, isbn13, my_rating,
                               avg_rating, exclusive_shelf, date_read, date_added)
            VALUES (:book_id, :title, :author, :isbn, :isbn13, :my_rating,
                    :avg_rating, :exclusive_shelf, :date_read, :date_added)
            ON CONFLICT(book_id) DO UPDATE SET
                title=excluded.title, author=excluded.author, isbn=excluded.isbn,
                isbn13=excluded.isbn13, my_rating=excluded.my_rating,
                avg_rating=excluded.avg_rating, exclusive_shelf=excluded.exclusive_shelf,
                date_read=excluded.date_read, date_added=excluded.date_added
            """,
            {
                "book_id": r.book_id, "title": r.title, "author": r.author,
                "isbn": r.isbn, "isbn13": r.isbn13, "my_rating": r.my_rating,
                "avg_rating": r.avg_rating, "exclusive_shelf": r.exclusive_shelf,
                "date_read": r.date_read, "date_added": r.date_added,
            },
        )
        conn.execute(
            """
            INSERT INTO reviews (book_id, review_html, review_text, has_spoiler, source)
            VALUES (:book_id, :review_html, :review_text, :has_spoiler, 'csv')
            ON CONFLICT(book_id) DO UPDATE SET
                review_html=excluded.review_html, review_text=excluded.review_text,
                has_spoiler=excluded.has_spoiler
            """,
            {
                "book_id": r.book_id, "review_html": r.review_html,
                "review_text": r.review_text, "has_spoiler": int(r.has_spoiler),
            },
        )
        for shelf in r.shelves:
            conn.execute("INSERT OR IGNORE INTO shelves (name) VALUES (?)", (shelf,))
            shelf_id = conn.execute(
                "SELECT shelf_id FROM shelves WHERE name = ?", (shelf,)
            ).fetchone()[0]
            conn.execute(
                "INSERT OR IGNORE INTO book_shelves (book_id, shelf_id) VALUES (?, ?)",
                (r.book_id, shelf_id),
            )
    conn.commit()
    return len(records)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gr_autopilot/store/repository.py tests/test_store.py
git commit -m "feat(store): idempotent upsert_books with shelves"
```

---

## Task 6: Repository — `targets()` (rated-reads-only)

**Files:** Modify `src/gr_autopilot/store/repository.py`; Modify `tests/test_store.py`

- [ ] **Step 1: Write the failing test**

```python
# append to tests/test_store.py
from gr_autopilot.store.repository import targets


def test_targets_rated_reads_only(conn):
    upsert_books(conn, parse_export(FIXTURE))
    rows = targets(conn, require_rating=True)
    # only book 22: read + empty review + rating > 0
    assert [r["book_id"] for r in rows] == [22]


def test_targets_include_unrated_when_disabled(conn):
    upsert_books(conn, parse_export(FIXTURE))
    # book 11 is read but reviewed (excluded); 33 is to-read (excluded);
    # with require_rating False still only 22 qualifies here (it is the only read+empty)
    rows = targets(conn, require_rating=False)
    assert [r["book_id"] for r in rows] == [22]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_store.py -k targets -v`
Expected: FAIL — `ImportError: cannot import name 'targets'`.

- [ ] **Step 3: Write minimal implementation** (append to `repository.py`)

```python
def targets(conn: sqlite3.Connection, require_rating: bool = True) -> list[sqlite3.Row]:
    """Read-but-unreviewed books. require_rating restricts to my_rating > 0 (sign-off default)."""
    query = """
        SELECT b.book_id, b.title, b.author, b.my_rating, b.date_read
        FROM books b
        JOIN reviews r ON r.book_id = b.book_id
        WHERE b.exclusive_shelf = 'read' AND r.is_empty = 1
    """
    if require_rating:
        query += " AND b.my_rating > 0"
    query += " ORDER BY b.date_read DESC"
    return conn.execute(query).fetchall()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_store.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/gr_autopilot/store/repository.py tests/test_store.py
git commit -m "feat(store): targets() query for rated read-but-unreviewed books"
```

---

## Task 7: CLI — `gr ingest` and `gr status`

**Files:** Create `src/gr_autopilot/cli.py`, `tests/test_cli.py`

- [ ] **Step 1: Write the failing test** (uses Typer's CliRunner; isolates db via env)

```python
# tests/test_cli.py
from pathlib import Path

from typer.testing import CliRunner

from gr_autopilot.cli import app

runner = CliRunner()
FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def test_ingest_then_status(tmp_path, monkeypatch):
    monkeypatch.setenv("GR_DB_PATH", str(tmp_path / "test.db"))

    result = runner.invoke(app, ["ingest", str(FIXTURE)])
    assert result.exit_code == 0, result.output
    assert "Ingested 3 books" in result.output

    result = runner.invoke(app, ["status"])
    assert result.exit_code == 0, result.output
    assert "books=3" in result.output
    assert "review_targets=1" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ModuleNotFoundError: gr_autopilot.cli`.

- [ ] **Step 3: Write minimal implementation**

```python
# src/gr_autopilot/cli.py
from pathlib import Path

import typer

from gr_autopilot.config import Settings
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.store.db import connect, init_db
from gr_autopilot.store.repository import targets, upsert_books

app = typer.Typer(help="goodreads-autopilot CLI")


def _open_db(settings: Settings):
    settings.db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = connect(settings.db_path)
    init_db(conn)
    return conn


@app.command()
def ingest(csv_path: Path) -> None:
    """Parse a Goodreads CSV export into the local store."""
    settings = Settings()
    conn = _open_db(settings)
    count = upsert_books(conn, parse_export(csv_path))
    typer.echo(f"Ingested {count} books into {settings.db_path}")


@app.command()
def status() -> None:
    """Show library size and how many books need a review."""
    settings = Settings()
    conn = _open_db(settings)
    total = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    n_targets = len(targets(conn, settings.require_rating))
    typer.echo(f"books={total} review_targets={n_targets}")


if __name__ == "__main__":
    app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 5: Verify the installed entrypoint works**

Run: `uv run gr status`
Expected: prints `books=0 review_targets=0` (fresh db) or current counts; exit 0.

- [ ] **Step 6: Commit**

```bash
git add src/gr_autopilot/cli.py tests/test_cli.py
git commit -m "feat(cli): gr ingest and gr status commands"
```

---

## Task 8: Full local quality gate green

**Files:** none (run the tools the CI will run)

- [ ] **Step 1: Format + lint**

Run: `uv run ruff format . && uv run ruff check .`
Expected: no errors. Fix any reported issues (most autofix with `ruff check --fix`).

- [ ] **Step 2: Type check**

Run: `uv run mypy`
Expected: `Success: no issues found`. Fix any typing gaps (add annotations; `sqlite3.Row` indexing is `Any`, acceptable).

- [ ] **Step 3: Security scan**

Run: `uv run bandit -c pyproject.toml -r src`
Expected: no issues of medium+ severity. (SQL uses parameterized queries — no B608.)

- [ ] **Step 4: Tests + coverage gate**

Run: `uv run pytest`
Expected: all pass, total coverage ≥ 80% (fails the run otherwise).

- [ ] **Step 5: Commit any fixes**

```bash
git add -A
git commit -m "chore: satisfy ruff/mypy/bandit/coverage gate" || echo "nothing to fix"
```

---

## Task 9: CI workflow — the PR quality gate

**Files:** Create `.github/workflows/ci.yml`

- [ ] **Step 1: Create `.github/workflows/ci.yml`**

```yaml
name: ci
on:
  pull_request:
    branches: [main]
  push:
    branches: [main]   # required for status checks to register on the default branch

permissions:
  contents: read

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8
        with:
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run ruff format --check .
      - run: uv run ruff check .

  typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8
        with:
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run mypy

  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8
        with:
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run pytest

  security:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v8
        with:
          enable-cache: true
      - run: uv sync --locked --dev
      - run: uv run bandit -c pyproject.toml -r src
```

- [ ] **Step 2: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: PR quality gate (lint/typecheck/test/security) on uv"
```

- [ ] **Step 3: (Manual, after first push to GitHub) register branch protection**

After the repo is on GitHub (private) and `ci.yml` has run once on `main`, create a ruleset requiring the four checks. Save as `ruleset.json`:

```json
{
  "name": "main-protection",
  "target": "branch",
  "enforcement": "active",
  "conditions": { "ref_name": { "include": ["refs/heads/main"], "exclude": [] } },
  "rules": [
    { "type": "pull_request",
      "parameters": { "required_approving_review_count": 0, "dismiss_stale_reviews_on_push": true } },
    { "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "lint" }, { "context": "typecheck" },
          { "context": "test" }, { "context": "security" }
        ] } }
  ]
}
```

Run: `gh api --method POST /repos/OWNER/REPO/rulesets --input ruleset.json`
(Note: the `-F` flag encoding 422s for nested rules — `--input` JSON is required.)

---

## Self-Review (completed by plan author)

- **Spec coverage:** §6.1 ingest → Tasks 2–3; §6.2 store (upsert idempotency, targets) → Tasks 4–6; §5 data model (books/reviews/shelves/book_shelves, generated `is_empty`, book_id PK) → Task 4; §8 `ci.yml` + ruleset → Task 9; config kill-switch field seeded → Task 1. Voice/generate/browser/actions/orchestrator/automation are **out of scope for Plan 01** (later plans).
- **Placeholder scan:** none — every step has runnable code/commands.
- **Type consistency:** `BookRecord` fields (Task 3) are consumed verbatim by `upsert_books` (Task 5); `targets()` signature `(conn, require_rating=True)` matches CLI call in Task 7 and tests in Task 6.
- **Deviation note:** `reviews` keyed by `book_id` (not `review_id`) and `actions_log`/`runs` deferred — recorded in File Structure section, intentional YAGNI.

## Next plans (written after this one is built & green)
- **Plan 02 — voice:** Embedder/VectorStore protocols, SentenceTransformerEmbedder (bge-small), ChromaStore, index build + retrieve.
- **Plan 03 — generate:** Claude client, cached voice prefix + RAG exemplars, draft generation, Batches path.
- **Plan 04 — browser + live capture:** Playwright storage_state login, stealth, login-health; §9 write-flow capture.
- **Plan 05 — actions + orchestrator + cli:** the quarantined write surface (reviews/ratings/shelves/tags/lists), `actions_log`/`runs`, dry-run + kill switch, full pipeline.
- **Plan 06 — automation.yml:** two-stage scheduled workflow (hosted generate → self-hosted post).
