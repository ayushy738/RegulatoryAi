import json
import re
from abc import ABC, abstractmethod
from typing import Any

from backend.core.config import settings

JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.MULTILINE)


class LLMClient(ABC):
    @abstractmethod
    def complete_json(self, system: str, user: str, model: str) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def complete_text(
        self,
        system: str,
        user: str,
        model: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        raise NotImplementedError


def _parse_json_response(content: str) -> dict[str, Any]:
    stripped = JSON_FENCE_RE.sub("", content.strip()).strip()
    return json.loads(stripped)


class OfflineClient(LLMClient):
    def complete_json(self, system: str, user: str, model: str) -> dict[str, Any]:
        return {
            "plain_english_summary": "AI summarisation is disabled until provider keys are added.",
            "why_it_matters": "Connect an LLM provider to generate grounded regulatory analysis.",
            "affected_segments": [],
            "important_dates": [],
            "action_required": "monitor",
            "confidence": "low",
            "evidence_quotes": [],
        }

    def complete_text(
        self,
        system: str,
        user: str,
        model: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        return (
            "I can show the workflow, but live insight chat needs an LLM API key. "
            "Once configured, I will answer only from the selected regulatory update."
        )


class AnthropicClient(LLMClient):
    def __init__(self) -> None:
        settings.require_llm()
        from anthropic import Anthropic

        self.client = Anthropic(api_key=settings.anthropic_api_key)

    def complete_json(self, system: str, user: str, model: str) -> dict[str, Any]:
        content = self.complete_text(
            system=f"{system}\nRespond with ONLY valid JSON, no prose, no markdown fences.",
            user=user,
            model=model,
        )
        try:
            return _parse_json_response(content)
        except json.JSONDecodeError:
            retry = self.complete_text(
                system="Return only the corrected valid JSON object from the previous answer.",
                user=content,
                model=model,
            )
            return _parse_json_response(retry)

    def complete_text(
        self,
        system: str,
        user: str,
        model: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        messages = [*(history or []), {"role": "user", "content": user}]
        response = self.client.messages.create(
            model=model,
            max_tokens=1200,
            system=system,
            messages=messages,
        )
        return "".join(block.text for block in response.content if getattr(block, "text", None))


class OpenAIClient(LLMClient):
    def __init__(self) -> None:
        settings.require_llm()
        from openai import OpenAI

        self.client = OpenAI(api_key=settings.openai_api_key)

    def complete_json(self, system: str, user: str, model: str) -> dict[str, Any]:
        content = self.complete_text(
            system=f"{system}\nRespond with ONLY valid JSON, no prose, no markdown fences.",
            user=user,
            model=model,
        )
        try:
            return _parse_json_response(content)
        except json.JSONDecodeError:
            retry = self.complete_text(
                system="Return only the corrected valid JSON object from the previous answer.",
                user=content,
                model=model,
            )
            return _parse_json_response(retry)

    def complete_text(
        self,
        system: str,
        user: str,
        model: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        messages = [
            {"role": "system", "content": system},
            *(history or []),
            {"role": "user", "content": user},
        ]
        response = self.client.chat.completions.create(model=model, messages=messages)
        return response.choices[0].message.content or ""


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "anthropic":
        return AnthropicClient()
    if settings.llm_provider == "openai":
        return OpenAIClient()
    return OfflineClient()
