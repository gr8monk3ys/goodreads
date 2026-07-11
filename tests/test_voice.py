import sqlite3

from gr_autopilot.store.repository import set_book_genres
from gr_autopilot.voice.index import build_index, retrieve
from gr_autopilot.voice.memory_store import InMemoryVectorStore, cosine
from gr_autopilot.voice.protocols import Embedder

_VOCAB = ["space", "war", "love", "magic", "robot", "ocean"]


class FakeEmbedder:
    """Deterministic bag-of-vocab embedder: texts sharing words get higher cosine."""

    @property
    def dimension(self) -> int:
        return len(_VOCAB)

    def _vec(self, text: str) -> list[float]:
        t = text.lower()
        return [float(t.count(w)) for w in _VOCAB]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


def test_fake_embedder_satisfies_protocol() -> None:
    assert isinstance(FakeEmbedder(), Embedder)


def test_cosine_basic() -> None:
    assert cosine([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine([1.0, 0.0], [0.0, 1.0]) == 0.0
    assert cosine([0.0, 0.0], [1.0, 1.0]) == 0.0


def test_inmemory_upsert_is_idempotent() -> None:
    store = InMemoryVectorStore()
    store.upsert(["1"], [[1.0, 0.0]], ["doc"], [{}])
    store.upsert(["1"], [[0.0, 1.0]], ["doc2"], [{}])
    assert store.count() == 1


def _seed(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO books (book_id, title, my_rating) VALUES (1, 'A', 5)")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (1, 'space war robot')")
    conn.execute("INSERT INTO books (book_id, title, my_rating) VALUES (2, 'B', 3)")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (2, 'love magic ocean')")
    conn.execute("INSERT INTO books (book_id, title, my_rating) VALUES (3, 'C', 4)")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (3, '')")  # empty -> skipped
    conn.commit()


def test_build_index_empty_returns_zero(conn: sqlite3.Connection) -> None:
    assert build_index(conn, FakeEmbedder(), InMemoryVectorStore()) == 0


def test_build_index_skips_empty_reviews(conn: sqlite3.Connection) -> None:
    _seed(conn)
    store = InMemoryVectorStore()
    assert build_index(conn, FakeEmbedder(), store) == 2
    assert store.count() == 2


def test_retrieve_ranks_relevant_first(conn: sqlite3.Connection) -> None:
    _seed(conn)
    store = InMemoryVectorStore()
    build_index(conn, FakeEmbedder(), store)
    top = retrieve("a space robot at war", FakeEmbedder(), store, k=1)
    assert len(top) == 1
    assert top[0].id == "1"


def test_retrieve_where_filter(conn: sqlite3.Connection) -> None:
    _seed(conn)
    store = InMemoryVectorStore()
    build_index(conn, FakeEmbedder(), store)
    res = retrieve("love magic", FakeEmbedder(), store, k=5, where={"rating": 5})
    assert [e.id for e in res] == ["1"]  # only book 1 has rating 5


def test_build_index_includes_genre_metadata(conn: sqlite3.Connection) -> None:
    conn.execute("INSERT INTO books (book_id, title, my_rating) VALUES (1, 'A', 5)")
    conn.execute("INSERT INTO reviews (book_id, review_text) VALUES (1, 'space war robot')")
    conn.commit()
    set_book_genres(conn, 1, ("Sci-Fi",))
    store = InMemoryVectorStore()
    build_index(conn, FakeEmbedder(), store)
    res = retrieve("space", FakeEmbedder(), store, k=5, where={"genre": "Sci-Fi"})
    assert [e.id for e in res] == ["1"]
