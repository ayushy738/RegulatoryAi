from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchHealth,
    RetrievalBranchOutcome,
    RetrievalBranchStatus,
)

EMBEDDING_HEALTH_SCHEMA_VERSION = "1"
EMBEDDING_HEALTH_POLICY_VERSION = "ask-ai-embedding-health-v1"


class EmbeddingCompatibilityState(StrEnum):
    READY = "ready"
    HEALTHY_EMPTY = "healthy_empty"
    PARTIAL_INDEX = "partial_index"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    PROVIDER_MISMATCH = "provider_mismatch"
    MODEL_MISMATCH = "model_mismatch"
    DIMENSION_MISMATCH = "dimension_mismatch"
    METADATA_UNAVAILABLE = "metadata_unavailable"
    INVALID_METADATA = "invalid_metadata"


class EmbeddingCompatibilityHealth(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    FAILED = "failed"


class EmbeddingIdentity(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
    )

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    dimension: int = Field(ge=1)


class ConfiguredEmbedding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    identity: EmbeddingIdentity
    configured: bool


class IndexedEmbeddingSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    identity: EmbeddingIdentity
    count: int = Field(ge=1)


class EmbeddingIndexObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    chunk_count: int = Field(ge=0)
    embedding_count: int = Field(ge=0)
    column_dimension: int = Field(ge=1)
    indexed_sets: tuple[IndexedEmbeddingSet, ...] = ()

    @model_validator(mode="after")
    def validate_inventory(self) -> Self:
        identities = tuple(item.identity for item in self.indexed_sets)
        if len(set(identities)) != len(identities):
            raise ValueError("Indexed embedding identities must be unique")
        if sum(item.count for item in self.indexed_sets) != self.embedding_count:
            raise ValueError("Embedding inventory count must match indexed sets")
        if self.chunk_count == 0 and self.embedding_count:
            raise ValueError("Embedding rows cannot exist without chunks")
        if any(item.count > self.chunk_count for item in self.indexed_sets):
            raise ValueError("One embedding identity cannot exceed chunk count")
        return self


class EmbeddingCompatibilityDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1"] = EMBEDDING_HEALTH_SCHEMA_VERSION
    policy_version: str = Field(
        default=EMBEDDING_HEALTH_POLICY_VERSION,
        min_length=1,
    )
    configured_identity: EmbeddingIdentity | None = None
    state: EmbeddingCompatibilityState
    health: EmbeddingCompatibilityHealth
    chunk_count: int | None = Field(default=None, ge=0)
    embedding_count: int | None = Field(default=None, ge=0)
    matching_embedding_count: int | None = Field(default=None, ge=0)
    can_query_vector: bool = False
    no_match_is_trustworthy: bool = False
    safe_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{0,99}$",
    )

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        healthy = self.state in {
            EmbeddingCompatibilityState.READY,
            EmbeddingCompatibilityState.HEALTHY_EMPTY,
        }
        degraded = self.state is EmbeddingCompatibilityState.PARTIAL_INDEX
        expected_health = (
            EmbeddingCompatibilityHealth.HEALTHY
            if healthy
            else (
                EmbeddingCompatibilityHealth.DEGRADED
                if degraded
                else EmbeddingCompatibilityHealth.FAILED
            )
        )
        if self.health is not expected_health:
            raise ValueError("Embedding compatibility state and health must agree")
        if healthy != (self.safe_code is None):
            raise ValueError("Only nonhealthy compatibility requires a safe code")
        expected_query = self.state in {
            EmbeddingCompatibilityState.READY,
            EmbeddingCompatibilityState.PARTIAL_INDEX,
        }
        if self.can_query_vector is not expected_query:
            raise ValueError("Vector query eligibility does not match compatibility")
        expected_no_match = self.state in {
            EmbeddingCompatibilityState.READY,
            EmbeddingCompatibilityState.HEALTHY_EMPTY,
        }
        if self.no_match_is_trustworthy is not expected_no_match:
            raise ValueError("No-match trust does not match compatibility")
        if self.state not in {
            EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE,
            EmbeddingCompatibilityState.METADATA_UNAVAILABLE,
            EmbeddingCompatibilityState.INVALID_METADATA,
        } and self.configured_identity is None:
            raise ValueError("Evaluated compatibility requires configured identity")
        return self


class HealthProvider(Protocol):
    def health(self) -> dict[str, Any]: ...


def evaluate_embedding_compatibility(
    configured: ConfiguredEmbedding,
    index: EmbeddingIndexObservation,
) -> EmbeddingCompatibilityDecision:
    identity = configured.identity
    if not configured.configured:
        return _decision(
            identity,
            EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE,
            index,
            safe_code="EMBEDDING_PROVIDER_UNAVAILABLE",
        )
    if identity.dimension != index.column_dimension:
        return _decision(
            identity,
            EmbeddingCompatibilityState.DIMENSION_MISMATCH,
            index,
            safe_code="EMBEDDING_DIMENSION_MISMATCH",
        )
    if index.embedding_count == 0:
        state = (
            EmbeddingCompatibilityState.HEALTHY_EMPTY
            if index.chunk_count == 0
            else EmbeddingCompatibilityState.PARTIAL_INDEX
        )
        return _decision(
            identity,
            state,
            index,
            matching=0,
            safe_code=(
                None
                if state is EmbeddingCompatibilityState.HEALTHY_EMPTY
                else "EMBEDDING_INDEX_PARTIAL"
            ),
        )
    provider_sets = tuple(
        item
        for item in index.indexed_sets
        if item.identity.provider == identity.provider
    )
    if not provider_sets:
        return _decision(
            identity,
            EmbeddingCompatibilityState.PROVIDER_MISMATCH,
            index,
            matching=0,
            safe_code="EMBEDDING_PROVIDER_MISMATCH",
        )
    model_sets = tuple(
        item
        for item in provider_sets
        if item.identity.model == identity.model
    )
    if not model_sets:
        return _decision(
            identity,
            EmbeddingCompatibilityState.MODEL_MISMATCH,
            index,
            matching=0,
            safe_code="EMBEDDING_MODEL_MISMATCH",
        )
    dimension_sets = tuple(
        item
        for item in model_sets
        if item.identity.dimension == identity.dimension
    )
    if not dimension_sets:
        return _decision(
            identity,
            EmbeddingCompatibilityState.DIMENSION_MISMATCH,
            index,
            matching=0,
            safe_code="EMBEDDING_DIMENSION_MISMATCH",
        )
    matching = dimension_sets[0].count
    state = (
        EmbeddingCompatibilityState.READY
        if matching == index.chunk_count
        else EmbeddingCompatibilityState.PARTIAL_INDEX
    )
    return _decision(
        identity,
        state,
        index,
        matching=matching,
        safe_code=(
            None
            if state is EmbeddingCompatibilityState.READY
            else "EMBEDDING_INDEX_PARTIAL"
        ),
    )


def inspect_runtime_embedding_compatibility(
    embedding_provider: HealthProvider,
    vector_store: HealthProvider,
) -> EmbeddingCompatibilityDecision:
    try:
        provider_health = embedding_provider.health()
    except Exception:
        return _unavailable("EMBEDDING_PROVIDER_UNAVAILABLE")
    try:
        configured = _configured_from_health(provider_health)
    except (KeyError, TypeError, ValueError, ValidationError):
        return _invalid_metadata()
    if not configured.configured:
        return _unavailable(
            "EMBEDDING_PROVIDER_UNAVAILABLE",
            identity=configured.identity,
        )
    try:
        vector_health = vector_store.health()
    except Exception:
        return _unavailable(
            "EMBEDDING_INDEX_METADATA_UNAVAILABLE",
            identity=configured.identity,
        )
    try:
        index = _index_from_health(vector_health)
    except (KeyError, TypeError, ValueError, ValidationError):
        return _invalid_metadata(configured.identity)
    return evaluate_embedding_compatibility(configured, index)


def vector_preflight_outcome(
    decision: EmbeddingCompatibilityDecision,
) -> RetrievalBranchOutcome | None:
    if decision.state is EmbeddingCompatibilityState.READY:
        return None
    if decision.state is EmbeddingCompatibilityState.HEALTHY_EMPTY:
        return RetrievalBranchOutcome(
            branch=RetrievalBranch.VECTOR,
            status=RetrievalBranchStatus.NO_MATCH,
            health=RetrievalBranchHealth.HEALTHY,
            duration_ms=0,
            match_count=0,
        )
    status = (
        RetrievalBranchStatus.PARTIAL
        if decision.state is EmbeddingCompatibilityState.PARTIAL_INDEX
        else (
            RetrievalBranchStatus.UNAVAILABLE
            if decision.state
            in {
                EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE,
                EmbeddingCompatibilityState.METADATA_UNAVAILABLE,
            }
            else RetrievalBranchStatus.INVALID_OUTPUT
        )
    )
    health = (
        RetrievalBranchHealth.DEGRADED
        if status is RetrievalBranchStatus.PARTIAL
        else RetrievalBranchHealth.FAILED
    )
    return RetrievalBranchOutcome(
        branch=RetrievalBranch.VECTOR,
        status=status,
        health=health,
        duration_ms=0,
        match_count=0,
        safe_failure_code=decision.safe_code,
    )


def _configured_from_health(value: object) -> ConfiguredEmbedding:
    if not isinstance(value, Mapping):
        raise TypeError("Embedding health must be a mapping")
    return ConfiguredEmbedding(
        identity=EmbeddingIdentity(
            provider=value["provider"],
            model=value["model"],
            dimension=value["dimension"],
        ),
        configured=value["configured"],
    )


def _index_from_health(value: object) -> EmbeddingIndexObservation:
    if not isinstance(value, Mapping):
        raise TypeError("Vector health must be a mapping")
    column_type = value["column_type"]
    if not isinstance(column_type, str):
        raise TypeError("Vector column type must be text")
    match = re.fullmatch(r"vector\((\d+)\)", column_type.strip().lower())
    if match is None:
        raise ValueError("Vector column dimension is unavailable")
    raw_sets = value["identities"]
    if not isinstance(raw_sets, list):
        raise TypeError("Embedding identities must be a list")
    indexed_sets = tuple(
        IndexedEmbeddingSet(
            identity=EmbeddingIdentity(
                provider=item["provider"],
                model=item["model"],
                dimension=item["dimension"],
            ),
            count=item["count"],
        )
        for item in raw_sets
        if isinstance(item, Mapping)
    )
    if len(indexed_sets) != len(raw_sets):
        raise TypeError("Embedding identity entry is invalid")
    return EmbeddingIndexObservation(
        chunk_count=value["chunks"],
        embedding_count=value["embeddings"],
        column_dimension=int(match.group(1)),
        indexed_sets=indexed_sets,
    )


def _decision(
    identity: EmbeddingIdentity,
    state: EmbeddingCompatibilityState,
    index: EmbeddingIndexObservation,
    *,
    matching: int | None = None,
    safe_code: str | None,
) -> EmbeddingCompatibilityDecision:
    return EmbeddingCompatibilityDecision(
        configured_identity=identity,
        state=state,
        health=(
            EmbeddingCompatibilityHealth.HEALTHY
            if state
            in {
                EmbeddingCompatibilityState.READY,
                EmbeddingCompatibilityState.HEALTHY_EMPTY,
            }
            else (
                EmbeddingCompatibilityHealth.DEGRADED
                if state is EmbeddingCompatibilityState.PARTIAL_INDEX
                else EmbeddingCompatibilityHealth.FAILED
            )
        ),
        chunk_count=index.chunk_count,
        embedding_count=index.embedding_count,
        matching_embedding_count=matching,
        can_query_vector=state
        in {
            EmbeddingCompatibilityState.READY,
            EmbeddingCompatibilityState.PARTIAL_INDEX,
        },
        no_match_is_trustworthy=state
        in {
            EmbeddingCompatibilityState.READY,
            EmbeddingCompatibilityState.HEALTHY_EMPTY,
        },
        safe_code=safe_code,
    )


def _unavailable(
    safe_code: str,
    *,
    identity: EmbeddingIdentity | None = None,
) -> EmbeddingCompatibilityDecision:
    state = (
        EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE
        if safe_code == "EMBEDDING_PROVIDER_UNAVAILABLE"
        else EmbeddingCompatibilityState.METADATA_UNAVAILABLE
    )
    return EmbeddingCompatibilityDecision(
        configured_identity=identity,
        state=state,
        health=EmbeddingCompatibilityHealth.FAILED,
        can_query_vector=False,
        no_match_is_trustworthy=False,
        safe_code=safe_code,
    )


def _invalid_metadata(
    identity: EmbeddingIdentity | None = None,
) -> EmbeddingCompatibilityDecision:
    return EmbeddingCompatibilityDecision(
        configured_identity=identity,
        state=EmbeddingCompatibilityState.INVALID_METADATA,
        health=EmbeddingCompatibilityHealth.FAILED,
        can_query_vector=False,
        no_match_is_trustworthy=False,
        safe_code="EMBEDDING_HEALTH_INVALID_METADATA",
    )
