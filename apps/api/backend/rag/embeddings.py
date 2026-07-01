from __future__ import annotations

import hashlib
import math
from abc import ABC, abstractmethod
from typing import Any

import httpx

from backend.core.config import settings


class EmbeddingProvider(ABC):
    provider_name: str
    model: str
    dimension: int

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        raise NotImplementedError

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(text) for text in texts]

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError


class ParallelEmbeddingProvider(EmbeddingProvider):
    provider_name = "parallel"

    def __init__(self) -> None:
        settings.require_embedding_provider()
        self.base_url = settings.parallel_base_url.rstrip("/")
        self.model = settings.embedding_model
        self.dimension = settings.embedding_dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {settings.parallel_api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        return _extract_embeddings(response.json())

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "dimension": self.dimension,
            "configured": bool(settings.parallel_api_key),
        }


class OpenAIEmbeddingProvider(EmbeddingProvider):
    provider_name = "openai"

    def __init__(self) -> None:
        settings.require_embedding_provider()
        self.base_url = settings.openai_compatible_embedding_base_url.rstrip("/")
        self.api_key = settings.openai_compatible_embedding_api_key or settings.openai_api_key
        self.model = settings.embedding_model
        self.dimension = settings.embedding_dimension

    def embed(self, text: str) -> list[float]:
        return self.embed_batch([text])[0]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        response = httpx.post(
            f"{self.base_url}/embeddings",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json={"model": self.model, "input": texts},
            timeout=60,
        )
        response.raise_for_status()
        return _extract_embeddings(response.json())

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "dimension": self.dimension,
            "configured": bool(self.api_key),
        }


class OfflineEmbeddingProvider(EmbeddingProvider):
    provider_name = "offline"

    def __init__(self) -> None:
        self.model = "deterministic-hash-v1"
        self.dimension = settings.embedding_dimension

    def embed(self, text: str) -> list[float]:
        values = [0.0] * self.dimension
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimension
            sign = -1.0 if digest[4] % 2 else 1.0
            values[index] += sign
        norm = math.sqrt(sum(value * value for value in values)) or 1.0
        return [value / norm for value in values]

    def health(self) -> dict[str, Any]:
        return {
            "provider": self.provider_name,
            "model": self.model,
            "dimension": self.dimension,
            "configured": True,
        }


class EmbeddingProviderFactory:
    @staticmethod
    def get_provider() -> EmbeddingProvider:
        if settings.embedding_provider == "parallel":
            return ParallelEmbeddingProvider()
        if settings.embedding_provider == "openai":
            return OpenAIEmbeddingProvider()
        return OfflineEmbeddingProvider()


def _extract_embeddings(payload: dict[str, Any]) -> list[list[float]]:
    data = payload.get("data")
    if isinstance(data, list):
        vectors = [item.get("embedding") for item in data if isinstance(item, dict)]
    else:
        vectors = payload.get("embeddings")
    if not isinstance(vectors, list) or not vectors:
        raise RuntimeError("Embedding provider returned no vectors.")
    parsed = []
    for vector in vectors:
        if not isinstance(vector, list):
            raise RuntimeError("Embedding provider returned an invalid vector.")
        parsed.append([float(value) for value in vector])
    return parsed


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in text.split() if token.strip()]
