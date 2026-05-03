"""LLM provider base class + factory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class LLMError(Exception):
    """Raised when an upstream provider fails — the API turns this into 502."""


@dataclass(slots=True)
class LLMResponse:
    content: str
    tokens_in: int | None = None
    tokens_out: int | None = None


class LLMProvider(Protocol):
    name: str

    async def generate(
        self, *, model: str, system: str, user: str, api_key: str
    ) -> LLMResponse:
        ...


def get_provider(name: str) -> LLMProvider:
    name_l = name.lower().strip()
    if name_l == "gemini":
        from cobweb.services.llm.gemini import GeminiProvider

        return GeminiProvider()
    if name_l == "openrouter":
        from cobweb.services.llm.openrouter import OpenRouterProvider

        return OpenRouterProvider()
    raise LLMError(f"unknown LLM provider: {name}")
