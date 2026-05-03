from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


Provider = Literal["gemini", "openrouter"]


class LLMSettingsResponse(BaseModel):
    provider: Provider | None = None
    model: str | None = None
    has_api_key: bool = False
    prompt_template: str
    updated_at: str | None = None


class LLMSettingsUpdate(BaseModel):
    provider: Provider
    model: str = Field(min_length=1, max_length=128)
    api_key: str | None = Field(default=None, description="omit to keep existing key")
    prompt_template: str = Field(min_length=10, max_length=8000)


class TranslateRequest(BaseModel):
    lang: Literal["th"] = "th"
    custom_prompt: str | None = Field(default=None, max_length=8000)
    refresh: bool = False


class TranslateResponse(BaseModel):
    finding_id: str
    lang: str
    provider: str
    model: str
    content: str
    cached: bool
    tokens_in: int | None = None
    tokens_out: int | None = None
    created_at: str
