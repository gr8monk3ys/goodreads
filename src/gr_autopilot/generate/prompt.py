from __future__ import annotations

from dataclasses import dataclass, field

from gr_autopilot.voice.protocols import Exemplar

DEFAULT_GUIDELINES = (
    "You write book reviews in the user's own voice. Study the example reviews below "
    "and match their diction, sentence rhythm, length, structure, and the way opinions "
    "are expressed. Write a single review of the target book in that same voice."
)

ANTI_AI_TELLS = (
    "Write like the examples, not like an AI. Avoid: em-dash overuse, the 'not just X "
    "but Y' construction, rule-of-three padding, inflated adjectives, vague attributions, "
    "and a hollow summarizing final sentence."
)


@dataclass(frozen=True)
class TargetBook:
    title: str
    author: str
    rating: int | None = None
    shelves: tuple[str, ...] = field(default_factory=tuple)


def build_system_blocks(
    exemplars: list[Exemplar], guidelines: str = DEFAULT_GUIDELINES
) -> list[dict[str, object]]:
    """Build the cacheable system prompt (guidelines + exemplars + anti-tells).

    Returns a single text block carrying cache_control so the whole stable prefix
    is cached across generations. Exemplars are emitted in the order given (the
    retriever returns them deterministically by score) to keep the prefix byte-stable.
    """
    examples = "\n\n".join(
        f"Example review (rating {e.metadata.get('rating', '?')}/5):\n{e.text}"
        for e in exemplars
    )
    text = f"{guidelines}\n\n{examples}\n\n{ANTI_AI_TELLS}"
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def build_user_text(book: TargetBook, target_words: int) -> str:
    """Build the per-book user turn (uncached — varies every call)."""
    rating = f"{book.rating}/5 stars" if book.rating else "unrated"
    shelves = ", ".join(book.shelves) if book.shelves else "none"
    return (
        f"Write a review of about {target_words} words, in my voice, of this book:\n"
        f"Title: {book.title}\n"
        f"Author: {book.author}\n"
        f"My rating: {rating}\n"
        f"My shelves: {shelves}"
    )
