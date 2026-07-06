"""LLM provider abstraction.

Three providers behind one interface:
  * anthropic  - Claude (cheap Haiku model).
  * openai     - GPT-4o-mini.
  * mock       - deterministic, no network, no cost. Lets you run and TEST the
                 entire system (queue, worker, cache, websockets) with zero
                 API keys. Set LLM_PROVIDER=mock.

Every provider returns raw text; the worker is responsible for parsing +
validating that text into a TriageResult. Keeping "call the model" and
"validate the output" separate is what makes retries clean.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.core.config import settings
from app.core.logging import get_logger
from app.services.prompts import SYSTEM_PROMPT, build_user_prompt

logger = get_logger("llm")


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_used: int


class LLMProvider(ABC):
    @abstractmethod
    async def classify(self, subject: str, body: str) -> LLMResponse: ...


class MockProvider(LLMProvider):
    """Deterministic fake AI. Picks a category from keywords so demos/tests
    produce sensible, repeatable output with no network call."""

    model = "mock-1"

    async def classify(self, subject: str, body: str) -> LLMResponse:
        text_blob = f"{subject} {body}".lower()
        rules = [
            ("refund", ["refund", "money back", "return"]),
            ("billing", ["charge", "charged", "invoice", "payment", "bill", "subscription"]),
            ("bug", ["error", "crash", "broken", "bug", "not working", "fails"]),
            ("account", ["login", "password", "sign in", "account", "locked", "access"]),
        ]
        category = "other"
        for cat, kws in rules:
            if any(k in text_blob for k in kws):
                category = cat
                break

        urgent_words = ["urgent", "asap", "immediately", "angry", "twice", "double", "lawsuit", "!!"]
        urgency = 5 + sum(1 for w in urgent_words if w in text_blob)
        urgency = max(1, min(10, urgency))

        payload = {
            "category": category,
            "urgency_score": urgency,
            "summary": f"{category.capitalize()} issue: {subject.strip()[:60]}",
            "suggested_reply": (
                "Hi, thanks for reaching out and sorry for the trouble. "
                "We're looking into this now and will follow up shortly with an update."
            ),
        }
        return LLMResponse(
            text=json.dumps(payload),
            model=self.model,
            tokens_used=len(text_blob.split()),
        )


class AnthropicProvider(LLMProvider):
    def __init__(self) -> None:
        from anthropic import AsyncAnthropic

        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.anthropic_model

    async def classify(self, subject: str, body: str) -> LLMResponse:
        msg = await self.client.messages.create(
            model=self.model,
            max_tokens=500,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(subject, body)}],
            timeout=settings.llm_timeout_seconds,
        )
        text = "".join(block.text for block in msg.content if block.type == "text")
        tokens = msg.usage.input_tokens + msg.usage.output_tokens
        return LLMResponse(text=text, model=self.model, tokens_used=tokens)


class OpenAIProvider(LLMProvider):
    """Works with OpenAI and any OpenAI-compatible endpoint (via base_url)."""

    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None) -> None:
        from openai import AsyncOpenAI

        self.client = AsyncOpenAI(
            api_key=api_key or settings.openai_api_key,
            base_url=base_url,  # None -> real OpenAI
        )
        self.model = model or settings.openai_model

    async def classify(self, subject: str, body: str) -> LLMResponse:
        resp = await self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(subject, body)},
            ],
            response_format={"type": "json_object"},
            timeout=settings.llm_timeout_seconds,
        )
        text = resp.choices[0].message.content or ""
        tokens = resp.usage.total_tokens if resp.usage else 0
        return LLMResponse(text=text, model=self.model, tokens_used=tokens)


class GroqProvider(OpenAIProvider):
    """Groq - OpenAI-compatible, very fast, generous free tier.

    Get a free key at https://console.groq.com/keys. Reuses the OpenAI client
    pointed at Groq's endpoint. Good models for triage:
      * llama-3.1-8b-instant      (fast, cheap, default)
      * llama-3.3-70b-versatile   (smarter, still fast)
    """

    def __init__(self) -> None:
        super().__init__(
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            model=settings.groq_model,
        )


def get_llm_provider() -> LLMProvider:
    provider = settings.llm_provider
    if provider == "anthropic":
        return AnthropicProvider()
    if provider == "openai":
        return OpenAIProvider()
    if provider == "groq":
        return GroqProvider()
    return MockProvider()
