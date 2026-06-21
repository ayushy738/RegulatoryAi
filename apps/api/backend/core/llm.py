import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.core.config import settings

logger = logging.getLogger(__name__)

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


class ParallelClient(LLMClient):
    def __init__(self) -> None:
        settings.require_llm()
        self.base_url = settings.parallel_base_url.rstrip("/")
        self.headers = {
            "Authorization": f"Bearer {settings.parallel_api_key}",
            "Content-Type": "application/json",
        }

    def complete_json(self, system: str, user: str, model: str) -> dict[str, Any]:
        content = self.complete_text(
            system=f"{system}\nRespond with ONLY valid JSON, no prose, no markdown fences.",
            user=user,
            model=model,
        )
        try:
            return _parse_json_response(content)
        except json.JSONDecodeError:
            logger.warning("Parallel AI returned unparseable JSON, using offline fallback")
            return OfflineClient().complete_json(system, user, model)

    def complete_text(
        self,
        system: str,
        user: str,
        model: str,
        history: list[dict[str, str]] | None = None,
    ) -> str:
        if not model or model == "offline-demo":
            return (
                "Parallel AI is configured, but LLM_MODEL_CHAT is not set. "
                "Add the model name to .env and restart the API."
            )
        messages = [
            {"role": "system", "content": system},
            *(history or []),
            {"role": "user", "content": user},
        ]
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json={"model": model, "messages": messages, "stream": False},
                timeout=60,
            )
            response.raise_for_status()
            payload = response.json()
            choice = payload["choices"][0]
            if message := choice.get("message"):
                return message.get("content") or ""
            return choice.get("delta", {}).get("content") or ""
        except httpx.HTTPStatusError as exc:
            detail = _safe_http_error_detail(exc.response)
            logger.error("Parallel AI HTTP error: %s", detail)
            raise RuntimeError(
                f"AI service returned an error (HTTP {exc.response.status_code}). Please try again."
            ) from exc
        except Exception as exc:
            logger.error("Parallel AI connection error: %s: %s", type(exc).__name__, exc)
            raise RuntimeError(
                "Unable to reach the AI service. Please try again in a moment."
            ) from exc


def get_llm_client() -> LLMClient:
    if settings.llm_provider == "anthropic":
        return AnthropicClient()
    if settings.llm_provider == "openai":
        return OpenAIClient()
    if settings.llm_provider == "parallel" or (
        settings.llm_provider == "offline" and settings.parallel_api_key
    ):
        return ParallelClient()
    return OfflineClient()


def _safe_http_error_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except json.JSONDecodeError:
        return f"HTTP {response.status_code}: {response.text[:300]}"

    error = payload.get("error")
    if isinstance(error, dict):
        message = error.get("message") or error.get("type") or payload
    else:
        message = payload.get("message") or payload.get("detail") or payload
    return f"HTTP {response.status_code}: {message}"
