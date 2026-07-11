import sqlite3
from pathlib import Path

from gr_autopilot.actions.core import NullBackend, Throttle
from gr_autopilot.catalog.protocols import BookMeta
from gr_autopilot.config import Settings
from gr_autopilot.generate.prompt import TargetBook
from gr_autopilot.ingest.csv_parser import parse_export
from gr_autopilot.orchestrator.run import prepare_corpus, review_unreviewed
from gr_autopilot.store.repository import upsert_books
from gr_autopilot.voice.memory_store import InMemoryVectorStore

FIXTURE = Path(__file__).parent / "fixtures" / "sample_export.csv"


def _gen(book: TargetBook) -> str:
    return f"My review of {book.title}."


def _throttle() -> Throttle:
    return Throttle(sleeper=lambda _: None)


def test_review_unreviewed_dry_run(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    summary = review_unreviewed(
        conn,
        generate_text=_gen,
        backend=NullBackend(),
        settings=Settings(),
        dry_run=True,
        throttle=_throttle(),
    )
    assert summary.planned == 1  # only book 22 (rated read, empty review)
    assert summary.done == 0
    assert summary.dry_run is True
    n = conn.execute(
        "SELECT COUNT(*) FROM actions_log WHERE status='dry_run'"
    ).fetchone()[0]
    assert n == 1


def test_review_unreviewed_live_with_null_backend(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    summary = review_unreviewed(
        conn,
        generate_text=_gen,
        backend=NullBackend(),
        settings=Settings(),
        dry_run=False,
        throttle=_throttle(),
    )
    assert summary.planned == 1
    assert summary.done == 1
    assert summary.failed == 0


def test_limit_caps_actions(conn: sqlite3.Connection) -> None:
    upsert_books(conn, parse_export(FIXTURE))
    summary = review_unreviewed(
        conn,
        generate_text=_gen,
        backend=NullBackend(),
        settings=Settings(),
        dry_run=True,
        throttle=_throttle(),
        limit=0,
    )
    assert summary.planned == 0


class _FakeEmbedder:
    @property
    def dimension(self) -> int:
        return 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class _FakeCatalog:
    def __init__(self, mapping: dict[int, BookMeta]) -> None:
        self._mapping = mapping

    def get_meta(self, book_id: int) -> BookMeta | None:
        return self._mapping.get(book_id)


def test_prepare_corpus_enriches_then_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO books (book_id, title, my_rating, exclusive_shelf) VALUES (1, 'A', 5, 'read')"
    )
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (1, 'great book')")
    conn.commit()
    store = InMemoryVectorStore()
    enriched, indexed = prepare_corpus(
        conn,
        embedder=_FakeEmbedder(),
        store=store,
        catalog=_FakeCatalog({1: BookMeta(book_id=1, title="A", genres=("Fantasy",))}),
    )
    assert enriched == 1
    assert indexed == 1
    # the enriched genre reached the index metadata
    res = store.query(_FakeEmbedder().embed_query("x"), k=5, where={"genre": "Fantasy"})
    assert [e.id for e in res] == ["1"]


def test_prepare_corpus_without_catalog_skips_enrich(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO books (book_id, title, my_rating) VALUES (1, 'A', 5)")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (1, 'great book')")
    conn.commit()
    enriched, indexed = prepare_corpus(
        conn, embedder=_FakeEmbedder(), store=InMemoryVectorStore()
    )
    assert enriched == 0
    assert indexed == 1
