from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.core.config import settings
from backend.rag.embedding_health import (
    EmbeddingCompatibilityDecision,
    EmbeddingCompatibilityState,
    EmbeddingIdentity,
    inspect_runtime_embedding_compatibility,
)
from backend.rag.embeddings import EmbeddingProvider, EmbeddingProviderFactory
from backend.rag.retrieval import RetrievalProvider, SupabaseHybridRetrieval
from backend.rag.vector_store import VectorStore, VectorStoreFactory

V2_PROVIDER_SCHEMA_VERSION = "1"
V2_PROVIDER_POLICY_VERSION = "ask-ai-v2-provider-configuration-v1"
SUPPORTED_RETRIEVAL_PROVIDER = "supabase"
SUPPORTED_VECTOR_PROVIDER = "supabase"
SUPPORTED_EMBEDDING_PROVIDERS = frozenset({"offline", "openai", "parallel"})
SUPPORTED_EMBEDDING_DIMENSION = 1536
OFFLINE_EMBEDDING_MODEL = "deterministic-hash-v1"


class ProviderConfigurationState(StrEnum):
    VALIDATED = "validated"
    UNSUPPORTED_RETRIEVAL = "unsupported_retrieval"
    UNSUPPORTED_VECTOR = "unsupported_vector"
    UNSUPPORTED_EMBEDDING = "unsupported_embedding"
    UNSUPPORTED_MODEL = "unsupported_model"
    UNSUPPORTED_DIMENSION = "unsupported_dimension"
    CREDENTIALS_MISSING = "credentials_missing"
    CONSTRUCTION_UNAVAILABLE = "construction_unavailable"
    IMPLEMENTATION_DRIFT = "implementation_drift"
    STARTUP_HEALTH_FAILED = "startup_health_failed"


class ProviderConfigurationHealth(StrEnum):
    HEALTHY = "healthy"
    FAILED = "failed"


class V2ProviderConfiguration(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )

    schema_version: Literal["1"] = V2_PROVIDER_SCHEMA_VERSION
    policy_version: str = Field(
        default=V2_PROVIDER_POLICY_VERSION,
        min_length=1,
    )
    retrieval_provider: str = Field(min_length=1)
    vector_provider: str = Field(min_length=1)
    embedding_provider: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(ge=1)
    embedding_credentials_available: bool

    @model_validator(mode="after")
    def require_canonical_provider_names(self) -> Self:
        for value in (
            self.retrieval_provider,
            self.vector_provider,
            self.embedding_provider,
        ):
            if value != value.lower():
                raise ValueError("Provider names must be canonical lowercase")
        return self


class ProviderImplementationIdentity(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )

    retrieval_provider: str = Field(min_length=1)
    vector_provider: str = Field(min_length=1)
    embedding_provider: str = Field(min_length=1)
    embedding_model: str = Field(min_length=1)
    embedding_dimension: int = Field(ge=1)


class ProviderConfigurationDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1"] = V2_PROVIDER_SCHEMA_VERSION
    policy_version: str = Field(min_length=1)
    state: ProviderConfigurationState
    health: ProviderConfigurationHealth
    declared: ProviderImplementationIdentity
    actual: ProviderImplementationIdentity | None = None
    embedding_health_state: EmbeddingCompatibilityState | None = None
    safe_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        healthy = self.state is ProviderConfigurationState.VALIDATED
        if self.health is not (
            ProviderConfigurationHealth.HEALTHY
            if healthy
            else ProviderConfigurationHealth.FAILED
        ):
            raise ValueError("Provider configuration state and health must agree")
        if healthy != (self.safe_code is None):
            raise ValueError("Only failed provider configuration needs a safe code")
        if healthy and (self.actual != self.declared):
            raise ValueError("Validated provider identity must match declaration")
        if self.state in {
            ProviderConfigurationState.IMPLEMENTATION_DRIFT,
            ProviderConfigurationState.STARTUP_HEALTH_FAILED,
        } and self.actual is None:
            raise ValueError("Runtime provider failure requires actual identity")
        return self


@dataclass(frozen=True, slots=True)
class V2ProviderBundle:
    retrieval: RetrievalProvider
    vector: VectorStore
    embedding: EmbeddingProvider
    identity: ProviderImplementationIdentity
    embedding_health: EmbeddingCompatibilityDecision


@dataclass(frozen=True, slots=True)
class V2ProviderConstruction:
    decision: ProviderConfigurationDecision
    bundle: V2ProviderBundle | None

    def __post_init__(self) -> None:
        if (self.bundle is not None) != (
            self.decision.state is ProviderConfigurationState.VALIDATED
        ):
            raise ValueError("Only validated provider construction returns a bundle")


EmbeddingFactory = Callable[[], EmbeddingProvider]
VectorFactory = Callable[[], VectorStore]
RetrievalFactory = Callable[[EmbeddingProvider, VectorStore], RetrievalProvider]


def v2_provider_configuration_from_settings(
    source: Any = settings,
) -> V2ProviderConfiguration:
    embedding_provider = source.embedding_provider
    credentials_available = (
        True
        if embedding_provider == "offline"
        else (
            _has_credential(
                source.openai_compatible_embedding_api_key
            )
            or _has_credential(source.openai_api_key)
            if embedding_provider == "openai"
            else _has_credential(source.parallel_api_key)
        )
    )
    return V2ProviderConfiguration(
        retrieval_provider=source.retrieval_provider,
        vector_provider=source.vector_provider,
        embedding_provider=embedding_provider,
        embedding_model=source.embedding_model,
        embedding_dimension=source.embedding_dimension,
        embedding_credentials_available=credentials_available,
    )


def validate_v2_provider_configuration(
    configuration: V2ProviderConfiguration,
) -> ProviderConfigurationDecision:
    declared = _declared_identity(configuration)
    if configuration.retrieval_provider != SUPPORTED_RETRIEVAL_PROVIDER:
        return _failure(
            configuration,
            declared,
            ProviderConfigurationState.UNSUPPORTED_RETRIEVAL,
            "V2_RETRIEVAL_PROVIDER_UNSUPPORTED",
        )
    if configuration.vector_provider != SUPPORTED_VECTOR_PROVIDER:
        return _failure(
            configuration,
            declared,
            ProviderConfigurationState.UNSUPPORTED_VECTOR,
            "V2_VECTOR_PROVIDER_UNSUPPORTED",
        )
    if configuration.embedding_provider not in SUPPORTED_EMBEDDING_PROVIDERS:
        return _failure(
            configuration,
            declared,
            ProviderConfigurationState.UNSUPPORTED_EMBEDDING,
            "V2_EMBEDDING_PROVIDER_UNSUPPORTED",
        )
    if (
        configuration.embedding_provider == "offline"
        and configuration.embedding_model != OFFLINE_EMBEDDING_MODEL
    ):
        return _failure(
            configuration,
            declared,
            ProviderConfigurationState.UNSUPPORTED_MODEL,
            "V2_EMBEDDING_MODEL_UNSUPPORTED",
        )
    if configuration.embedding_dimension != SUPPORTED_EMBEDDING_DIMENSION:
        return _failure(
            configuration,
            declared,
            ProviderConfigurationState.UNSUPPORTED_DIMENSION,
            "V2_EMBEDDING_DIMENSION_UNSUPPORTED",
        )
    if (
        configuration.embedding_provider in {"openai", "parallel"}
        and not configuration.embedding_credentials_available
    ):
        return _failure(
            configuration,
            declared,
            ProviderConfigurationState.CREDENTIALS_MISSING,
            "V2_EMBEDDING_CREDENTIALS_MISSING",
        )
    return ProviderConfigurationDecision(
        policy_version=configuration.policy_version,
        state=ProviderConfigurationState.VALIDATED,
        health=ProviderConfigurationHealth.HEALTHY,
        declared=declared,
        actual=declared,
    )


def construct_v2_provider_bundle(
    configuration: V2ProviderConfiguration,
    *,
    embedding_factory: EmbeddingFactory = EmbeddingProviderFactory.get_provider,
    vector_factory: VectorFactory = VectorStoreFactory.get_provider,
    retrieval_factory: RetrievalFactory = lambda embedding, vector: (
        SupabaseHybridRetrieval(
            embedding_provider=embedding,
            vector_store=vector,
        )
    ),
) -> V2ProviderConstruction:
    validation = validate_v2_provider_configuration(configuration)
    if validation.state is not ProviderConfigurationState.VALIDATED:
        return V2ProviderConstruction(decision=validation, bundle=None)
    try:
        embedding = embedding_factory()
        vector = vector_factory()
        retrieval = retrieval_factory(embedding, vector)
    except Exception:
        return V2ProviderConstruction(
            decision=_failure(
                configuration,
                validation.declared,
                ProviderConfigurationState.CONSTRUCTION_UNAVAILABLE,
                "V2_PROVIDER_CONSTRUCTION_UNAVAILABLE",
            ),
            bundle=None,
        )
    actual = ProviderImplementationIdentity(
        retrieval_provider=retrieval.provider_name,
        vector_provider=vector.provider_name,
        embedding_provider=embedding.provider_name,
        embedding_model=embedding.model,
        embedding_dimension=embedding.dimension,
    )
    if actual != validation.declared:
        return V2ProviderConstruction(
            decision=_failure(
                configuration,
                validation.declared,
                ProviderConfigurationState.IMPLEMENTATION_DRIFT,
                "V2_PROVIDER_IMPLEMENTATION_DRIFT",
                actual=actual,
            ),
            bundle=None,
        )
    compatibility = inspect_runtime_embedding_compatibility(
        embedding,
        vector,
    )
    expected_embedding_identity = EmbeddingIdentity(
        provider=actual.embedding_provider,
        model=actual.embedding_model,
        dimension=actual.embedding_dimension,
    )
    if (
        compatibility.configured_identity is not None
        and compatibility.configured_identity != expected_embedding_identity
    ):
        health_identity = compatibility.configured_identity
        health_actual = ProviderImplementationIdentity(
            retrieval_provider=actual.retrieval_provider,
            vector_provider=actual.vector_provider,
            embedding_provider=health_identity.provider,
            embedding_model=health_identity.model,
            embedding_dimension=health_identity.dimension,
        )
        return V2ProviderConstruction(
            decision=_failure(
                configuration,
                validation.declared,
                ProviderConfigurationState.IMPLEMENTATION_DRIFT,
                "V2_PROVIDER_IMPLEMENTATION_DRIFT",
                actual=health_actual,
                embedding_health_state=compatibility.state,
            ),
            bundle=None,
        )
    if compatibility.state not in {
        EmbeddingCompatibilityState.READY,
        EmbeddingCompatibilityState.HEALTHY_EMPTY,
    }:
        return V2ProviderConstruction(
            decision=_failure(
                configuration,
                validation.declared,
                ProviderConfigurationState.STARTUP_HEALTH_FAILED,
                "V2_PROVIDER_STARTUP_HEALTH_FAILED",
                actual=actual,
                embedding_health_state=compatibility.state,
            ),
            bundle=None,
        )
    decision = ProviderConfigurationDecision(
        policy_version=configuration.policy_version,
        state=ProviderConfigurationState.VALIDATED,
        health=ProviderConfigurationHealth.HEALTHY,
        declared=validation.declared,
        actual=actual,
        embedding_health_state=compatibility.state,
    )
    return V2ProviderConstruction(
        decision=decision,
        bundle=V2ProviderBundle(
            retrieval=retrieval,
            vector=vector,
            embedding=embedding,
            identity=actual,
            embedding_health=compatibility,
        ),
    )


def _declared_identity(
    configuration: V2ProviderConfiguration,
) -> ProviderImplementationIdentity:
    return ProviderImplementationIdentity(
        retrieval_provider=configuration.retrieval_provider,
        vector_provider=configuration.vector_provider,
        embedding_provider=configuration.embedding_provider,
        embedding_model=configuration.embedding_model,
        embedding_dimension=configuration.embedding_dimension,
    )


def _failure(
    configuration: V2ProviderConfiguration,
    declared: ProviderImplementationIdentity,
    state: ProviderConfigurationState,
    safe_code: str,
    *,
    actual: ProviderImplementationIdentity | None = None,
    embedding_health_state: EmbeddingCompatibilityState | None = None,
) -> ProviderConfigurationDecision:
    return ProviderConfigurationDecision(
        policy_version=configuration.policy_version,
        state=state,
        health=ProviderConfigurationHealth.FAILED,
        declared=declared,
        actual=actual,
        embedding_health_state=embedding_health_state,
        safe_code=safe_code,
    )


def _has_credential(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())
