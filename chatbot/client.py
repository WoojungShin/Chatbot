"""Claude API streaming wrapper."""
from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass, field

import anthropic


def default_model() -> str:
    return os.getenv("CLAUDE_MODEL", "claude-sonnet-5")


class EmptyReply(RuntimeError):
    """모델이 텍스트를 하나도 돌려주지 않았다. 원인을 메시지에 담는다."""


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

    def complete(
        self,
        system_prompt: str,
        messages: list[dict],
        cfg: GenConfig | None = None,
    ) -> str:
        """한 번에 받아온다. 스트리밍과 달리 중간에 끊겨 유실될 조각이 없다."""
        cfg = cfg or GenConfig()
        msg = self._client.messages.create(
            model=cfg.model,
            max_tokens=cfg.max_tokens,
            system=[{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}],
            messages=messages,
        )
        self.last_usage = msg.usage
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        if not text.strip():
            # 왜 비었는지 남긴다. stop_reason이 max_tokens면 상한이 너무 낮은 것이고,
            # refusal이면 API가 거절한 것이다. 둘은 대응이 다르다.
            kinds = [getattr(b, "type", "?") for b in msg.content] or ["(없음)"]
            raise EmptyReply(
                f"텍스트가 없는 응답 (stop_reason={msg.stop_reason}, "
                f"블록={kinds}, output_tokens={msg.usage.output_tokens})"
            )
        return text
