"""Claude API streaming wrapper."""
from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic


def default_model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-5")


@dataclass
class GenConfig:
    model: str = field(default_factory=default_model)
    max_tokens: int = 1024


class ChatClient:
    def __init__(self, api_key: str | None = None):
        self._client = anthropic.Anthropic(api_key=api_key or os.getenv("ANTHROPIC_API_KEY"))
        self.last_usage = None

    def stream(
        self,
        system_prompt: str,
        messages: list[dict],
        cfg: GenConfig | None = None,
    ) -> Iterator[str]:
        """텍스트 조각을 yield. 종료 후 self.last_usage에 token 사용량 저장."""
        cfg = cfg or GenConfig()
        with self._client.messages.stream(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            # system prompt(원칙+예시)는 매 턴 동일하므로 caching
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        ) as s:
            yield from s.text_stream
            self.last_usage = s.get_final_message().usage
