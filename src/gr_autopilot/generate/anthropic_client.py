from __future__ import annotations

from typing import TYPE_CHECKING, cast

from gr_autopilot.generate.client import GenerationResult

if TYPE_CHECKING:  # anthropic is an optional extra; import types only for mypy
    from anthropic.types import TextBlockParam


class AnthropicChatClient:
    """Real Claude client (anthropic SDK). Requires the `generate` extra + ANTHROPIC_API_KEY.

    The system prompt's last block carries cache_control (set by build_system_blocks),
    so the voice prefix is cached across calls. Per 2026 models we pass neither
    `temperature` nor `budget_tokens` (rejected by Opus 4.8); thinking is adaptive.
    """

    def __init__(self, api_key: str | None = None) -> None:
        import anthropic

        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def generate(
        self,
        system_blocks: list[dict[str, object]],
        user_text: str,
        model: str,
        max_tokens: int,
    ) -> GenerationResult:
        resp = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=cast("list[TextBlockParam]", system_blocks),
            messages=[{"role": "user", "content": user_text}],
            thinking={"type": "adaptive"},
        )
        text = "".join(
            getattr(block, "text", "")
            for block in resp.content
            if getattr(block, "type", "") == "text"
        )
        usage = resp.usage
        return GenerationResult(
            text=text,
            input_tokens=int(getattr(usage, "input_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "output_tokens", 0) or 0),
            cache_read_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        )
