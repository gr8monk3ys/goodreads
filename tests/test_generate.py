from gr_autopilot.generate.client import GenerationResult
from gr_autopilot.generate.generator import generate_review
from gr_autopilot.generate.prompt import (
    ANTI_AI_TELLS,
    TargetBook,
    build_system_blocks,
    build_user_text,
)
from gr_autopilot.voice.memory_store import InMemoryVectorStore
from gr_autopilot.voice.protocols import Exemplar


class FakeEmbedder:
    @property
    def dimension(self) -> int:
        return 2

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [[1.0, 0.0] for _ in texts]

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0]


class FakeChatClient:
    def __init__(self, text: str) -> None:
        self.text = text
        self.calls: list[tuple[list[dict[str, object]], str, str, int]] = []

    def generate(
        self,
        system_blocks: list[dict[str, object]],
        user_text: str,
        model: str,
        max_tokens: int,
    ) -> GenerationResult:
        self.calls.append((system_blocks, user_text, model, max_tokens))
        return GenerationResult(text=self.text, cache_read_tokens=123)


def _exemplar() -> Exemplar:
    return Exemplar(
        id="1", text="A tight, funny little book.", score=1.0, metadata={"rating": 5}
    )


def test_system_blocks_carry_cache_control_and_examples() -> None:
    blocks = build_system_blocks([_exemplar()])
    assert blocks[-1]["cache_control"] == {"type": "ephemeral"}
    text = blocks[-1]["text"]
    assert isinstance(text, str)
    assert "A tight, funny little book." in text
    assert ANTI_AI_TELLS in text


def test_user_text_contains_metadata() -> None:
    book = TargetBook(
        title="Dune", author="Frank Herbert", rating=5, shelves=("sci-fi",)
    )
    text = build_user_text(book, target_words=120)
    assert "Dune" in text
    assert "Frank Herbert" in text
    assert "5/5 stars" in text
    assert "120 words" in text


def _store_with_exemplar() -> InMemoryVectorStore:
    store = InMemoryVectorStore()
    store.upsert(["1"], [[1.0, 0.0]], ["A tight, funny little book."], [{"rating": 5}])
    return store


def test_generate_review_uses_exemplars_and_passes_cache_control() -> None:
    client = FakeChatClient(text="word " * 150)
    draft = generate_review(
        TargetBook(title="Dune", author="Frank Herbert", rating=5),
        client=client,
        embedder=FakeEmbedder(),
        store=_store_with_exemplar(),
        target_words=150,
    )
    assert draft.within_target is True
    assert draft.word_count == 150
    assert draft.result.cache_read_tokens == 123
    # the exemplar reached the model via the cached system prompt
    system_blocks = client.calls[0][0]
    assert "A tight, funny little book." in str(system_blocks[-1]["text"])


def test_generate_review_flags_off_target_length() -> None:
    client = FakeChatClient(text="too short")
    draft = generate_review(
        TargetBook(title="Dune", author="Frank Herbert"),
        client=client,
        embedder=FakeEmbedder(),
        store=_store_with_exemplar(),
        target_words=150,
    )
    assert draft.within_target is False
