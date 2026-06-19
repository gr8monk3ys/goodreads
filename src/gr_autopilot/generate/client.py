from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class GenerationResult:
    text: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0


class ChatClient(Protocol):
    """A minimal chat-completion interface so generation is testable without a real LLM."""

    def generate(
        self,
        system_blocks: list[dict[str, object]],
        user_text: str,
        model: str,
        max_tokens: int,
    ) -> GenerationResult: ...
