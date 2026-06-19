from __future__ import annotations

from dataclasses import dataclass

from gr_autopilot.generate.client import ChatClient, GenerationResult
from gr_autopilot.generate.prompt import TargetBook, build_system_blocks, build_user_text
from gr_autopilot.voice.index import retrieve
from gr_autopilot.voice.protocols import Embedder, VectorStore


@dataclass(frozen=True)
class ReviewDraft:
    book_title: str
    text: str
    word_count: int
    within_target: bool
    result: GenerationResult


def generate_review(
    book: TargetBook,
    *,
    client: ChatClient,
    embedder: Embedder,
    store: VectorStore,
    model: str = "claude-sonnet-4-6",
    k: int = 5,
    target_words: int = 150,
    tolerance: float = 0.5,
    max_tokens: int = 2000,
) -> ReviewDraft:
    """Retrieve voice exemplars, prompt the model, and return a validated draft."""
    exemplars = retrieve(f"{book.title} by {book.author}", embedder, store, k=k)
    system_blocks = build_system_blocks(exemplars)
    user_text = build_user_text(book, target_words)
    result = client.generate(system_blocks, user_text, model=model, max_tokens=max_tokens)
    word_count = len(result.text.split())
    low, high = target_words * (1 - tolerance), target_words * (1 + tolerance)
    return ReviewDraft(
        book_title=book.title,
        text=result.text,
        word_count=word_count,
        within_target=low <= word_count <= high,
        result=result,
    )
