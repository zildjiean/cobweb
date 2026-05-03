"""OpenRouter (OpenAI-compatible) provider."""

from __future__ import annotations

import httpx

from cobweb.services.llm.base import LLMError, LLMResponse


_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterProvider:
    name = "openrouter"

    async def generate(
        self, *, model: str, system: str, user: str, api_key: str
    ) -> LLMResponse:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.2,
        }
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cobweb.local",
            "X-Title": "Cobweb",
        }
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(_URL, json=payload, headers=headers)
        if r.status_code >= 400:
            raise LLMError(f"openrouter {r.status_code}: {r.text[:300]}")
        data = r.json()
        choices = data.get("choices") or []
        if not choices:
            raise LLMError("openrouter: empty choices")
        text = (choices[0].get("message") or {}).get("content", "").strip()
        if not text:
            raise LLMError("openrouter: empty content")
        usage = data.get("usage") or {}
        return LLMResponse(
            content=text,
            tokens_in=usage.get("prompt_tokens"),
            tokens_out=usage.get("completion_tokens"),
        )
