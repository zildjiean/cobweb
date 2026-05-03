"""Google Gemini (generativelanguage.googleapis.com) provider."""

from __future__ import annotations

import httpx

from cobweb.services.llm.base import LLMError, LLMResponse


_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


class GeminiProvider:
    name = "gemini"

    async def generate(
        self, *, model: str, system: str, user: str, api_key: str
    ) -> LLMResponse:
        url = f"{_BASE}/{model}:generateContent"
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": 0.2},
        }
        headers = {"x-goog-api-key": api_key, "content-type": "application/json"}
        async with httpx.AsyncClient(timeout=60.0) as client:
            r = await client.post(url, json=payload, headers=headers)
        if r.status_code >= 400:
            raise LLMError(f"gemini {r.status_code}: {r.text[:300]}")
        data = r.json()
        candidates = data.get("candidates") or []
        if not candidates:
            raise LLMError("gemini: empty candidates")
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            raise LLMError("gemini: empty text")
        usage = data.get("usageMetadata") or {}
        return LLMResponse(
            content=text,
            tokens_in=usage.get("promptTokenCount"),
            tokens_out=usage.get("candidatesTokenCount"),
        )
