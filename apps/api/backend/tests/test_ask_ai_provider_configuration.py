from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from backend.rag.embedding_health import EmbeddingCompatibilityState
from backend.rag.models import (
    RetrievalBranch,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.provider_configuration import (
    OFFLINE_EMBEDDING_MODEL,
    SUPPORTED_EMBEDDING_DIMENSION,
    ProviderConfigurationDecision,
    ProviderConfigurationHealth,
    ProviderConfigurationState,
    ProviderImplementationIdentity,
    V2ProviderConfiguration,
    construct_v2_provider_bundle,
    v2_provider_configuration_from_settings,
    validate_v2_provider_configuration,
)
from backend.rag.retrieval import SupabaseHybridRetrieval
from backend.rag.vector_store import SupabasePgVectorStore, VectorStoreFactory


def _configuration(
    *,
    retrieval_provider: str = "supabase",
    vector_provider: str = "supabase",
    embedding_provider: str = "offline",
    embedding_model: str = OFFLINE_EMBEDDING_MODEL,
    embedding_dimension: int = SUPPORTED_EMBEDDING_DIMENSION,
    embedding_credentials_available: bool = True,
) -> V2ProviderConfiguration:
    return V2ProviderConfiguration(
        retrieval_provider=retrieval_provider,
        vector_provider=vector_provider,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_dimension=embedding_dimension,
        embedding_credentials_available=embedding_credentials_available,
    )


def _provider_health(
    *,
    provider: str = "offline",
    model: str = OFFLINE_EMBEDDING_MODEL,
    dimension: int = SUPPORTED_EMBEDDING_DIMENSION,
    configured: bool = True,
) -> dict[str, Any]:
    return {
        "provider": provider,
        "model": model,
        "dimension": dimension,
        "configured": configured,
    }


def _vector_health(
    *,
    chunks: int = 0,
    provider: str = "offline",
    model: str = OFFLINE_EMBEDDING_MODEL,
    dimension: int = SUPPORTED_EMBEDDING_DIMENSION,
) -> dict[str, Any]:
    identities = (
        [
            {
                "provider": provider,
                "model": model,
                "dimension": dimension,
                "count": chunks,
            }
        ]
        if chunks
        else []
    )
    return {
        "provider": "supabase",
        "chunks": chunks,
        "embeddings": chunks,
        "column_type": f"vector({dimension})",
        "identities": identities,
    }


class _Embedding:
    def __init__(
        self,
        *,
        provider: str = "offline",
        model: str = OFFLINE_EMBEDDING_MODEL,
        dimension: int = SUPPORTED_EMBEDDING_DIMENSION,
        health: dict[str, Any] | None = None,
    ) -> None:
        self.provider_name = provider
        self.model = model
        self.dimension = dimension
        self._health = health or _provider_health(
            provider=provider,
            model=model,
            dimension=dimension,
        )
        self.embed_calls: list[str] = []

    def embed(self, text: str) -> list[float]:
        self.embed_calls.append(text)
        return [0.25] * self.dimension

    def health(self) -> dict[str, Any]:
        return self._health


class _Vector:
    def __init__(
        self,
        *,
        provider: str = "supabase",
        health: dict[str, Any] | None = None,
        hits: list[RetrievalHit] | None = None,
    ) -> None:
        self.provider_name = provider
        self._health = health or _vector_health()
        self.hits = hits or []
        self.search_calls: list[tuple[int, int, int | None]] = []

    def health(self) -> dict[str, Any]:
        return self._health

    def similarity_search(
        self,
        embedding: list[float],
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        self.search_calls.append((len(embedding), limit, event_id))
        return self.hits


class _Retrieval:
    def __init__(self, provider: str = "supabase") -> None:
        self.provider_name = provider


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        ("offline", OFFLINE_EMBEDDING_MODEL),
        ("openai", "text-embedding-3-small"),
        ("parallel", "text-embedding-3-small"),
    ],
)
def test_supported_provider_matrix_validates(
    provider: str,
    model: str,
) -> None:
    decision = validate_v2_provider_configuration(
        _configuration(
            embedding_provider=provider,
            embedding_model=model,
        )
    )

    assert decision.state is ProviderConfigurationState.VALIDATED
    assert decision.health is ProviderConfigurationHealth.HEALTHY
    assert decision.actual == decision.declared
    assert decision.safe_code is None


@pytest.mark.parametrize(
    ("overrides", "state", "safe_code"),
    [
        (
            {"retrieval_provider": "memory"},
            ProviderConfigurationState.UNSUPPORTED_RETRIEVAL,
            "V2_RETRIEVAL_PROVIDER_UNSUPPORTED",
        ),
        (
            {"vector_provider": "memory"},
            ProviderConfigurationState.UNSUPPORTED_VECTOR,
            "V2_VECTOR_PROVIDER_UNSUPPORTED",
        ),
        (
            {"embedding_provider": "local"},
            ProviderConfigurationState.UNSUPPORTED_EMBEDDING,
            "V2_EMBEDDING_PROVIDER_UNSUPPORTED",
        ),
        (
            {"embedding_model": "text-embedding-3-small"},
            ProviderConfigurationState.UNSUPPORTED_MODEL,
            "V2_EMBEDDING_MODEL_UNSUPPORTED",
        ),
        (
            {"embedding_dimension": 768},
            ProviderConfigurationState.UNSUPPORTED_DIMENSION,
            "V2_EMBEDDING_DIMENSION_UNSUPPORTED",
        ),
        (
            {
                "embedding_provider": "openai",
                "embedding_model": "text-embedding-3-small",
                "embedding_credentials_available": False,
            },
            ProviderConfigurationState.CREDENTIALS_MISSING,
            "V2_EMBEDDING_CREDENTIALS_MISSING",
        ),
        (
            {
                "embedding_provider": "parallel",
                "embedding_model": "text-embedding-3-small",
                "embedding_credentials_available": False,
            },
            ProviderConfigurationState.CREDENTIALS_MISSING,
            "V2_EMBEDDING_CREDENTIALS_MISSING",
        ),
    ],
)
def test_unsupported_configuration_fails_with_stable_safe_code(
    overrides: dict[str, Any],
    state: ProviderConfigurationState,
    safe_code: str,
) -> None:
    values = _configuration().model_dump()
    values.update(overrides)

    first = validate_v2_provider_configuration(V2ProviderConfiguration(**values))
    second = validate_v2_provider_configuration(V2ProviderConfiguration(**values))

    assert first == second
    assert first.state is state
    assert first.health is ProviderConfigurationHealth.FAILED
    assert first.actual is None
    assert first.safe_code == safe_code
    assert "api_key" not in first.model_dump_json()


def test_offline_provider_does_not_require_credentials() -> None:
    decision = validate_v2_provider_configuration(
        _configuration(embedding_credentials_available=False)
    )

    assert decision.state is ProviderConfigurationState.VALIDATED


def test_settings_snapshot_resolves_credentials_without_storing_secrets() -> None:
    source = SimpleNamespace(
        retrieval_provider="supabase",
        vector_provider="supabase",
        embedding_provider="openai",
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
        openai_compatible_embedding_api_key="compatible-secret",
        openai_api_key=None,
        parallel_api_key=None,
    )

    configuration = v2_provider_configuration_from_settings(source)

    assert configuration.embedding_credentials_available is True
    assert "secret" not in configuration.model_dump_json()


@pytest.mark.parametrize("credential", [None, "", "   "])
def test_settings_snapshot_treats_blank_remote_credentials_as_missing(
    credential: str | None,
) -> None:
    source = SimpleNamespace(
        retrieval_provider="supabase",
        vector_provider="supabase",
        embedding_provider="parallel",
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
        openai_compatible_embedding_api_key=None,
        openai_api_key=None,
        parallel_api_key=credential,
    )

    configuration = v2_provider_configuration_from_settings(source)
    decision = validate_v2_provider_configuration(configuration)

    assert configuration.embedding_credentials_available is False
    assert decision.state is ProviderConfigurationState.CREDENTIALS_MISSING


def test_settings_snapshot_exposes_legacy_offline_model_drift() -> None:
    source = SimpleNamespace(
        retrieval_provider="supabase",
        vector_provider="supabase",
        embedding_provider="offline",
        embedding_model="text-embedding-3-small",
        embedding_dimension=1536,
        openai_compatible_embedding_api_key=None,
        openai_api_key=None,
        parallel_api_key=None,
    )

    configuration = v2_provider_configuration_from_settings(source)
    decision = validate_v2_provider_configuration(configuration)

    assert decision.state is ProviderConfigurationState.UNSUPPORTED_MODEL
    assert decision.safe_code == "V2_EMBEDDING_MODEL_UNSUPPORTED"


@pytest.mark.parametrize(
    "field",
    [
        "retrieval_provider",
        "vector_provider",
        "embedding_provider",
        "embedding_model",
        "embedding_dimension",
    ],
)
def test_constructed_identity_must_equal_every_declared_field(field: str) -> None:
    embedding = _Embedding()
    vector = _Vector()
    retrieval = _Retrieval()
    if field == "retrieval_provider":
        retrieval.provider_name = "other"
    elif field == "vector_provider":
        vector.provider_name = "other"
    elif field == "embedding_provider":
        embedding.provider_name = "other"
    elif field == "embedding_model":
        embedding.model = "other-model"
    else:
        embedding.dimension = 768

    result = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=lambda: embedding,
        vector_factory=lambda: vector,
        retrieval_factory=lambda _embedding, _vector: retrieval,
    )

    assert result.bundle is None
    assert result.decision.state is ProviderConfigurationState.IMPLEMENTATION_DRIFT
    assert result.decision.actual is not None
    assert (
        getattr(result.decision.actual, field)
        != getattr(result.decision.declared, field)
    )
    assert result.decision.safe_code == "V2_PROVIDER_IMPLEMENTATION_DRIFT"


@pytest.mark.parametrize(
    ("vector_health", "expected_state"),
    [
        (
            {
                "provider": "supabase",
                "chunks": 2,
                "embeddings": 1,
                "column_type": "vector(1536)",
                "identities": [
                    {
                        "provider": "offline",
                        "model": OFFLINE_EMBEDDING_MODEL,
                        "dimension": 1536,
                        "count": 1,
                    }
                ],
            },
            EmbeddingCompatibilityState.PARTIAL_INDEX,
        ),
        (
            _vector_health(
                chunks=1,
                provider="openai",
                model="text-embedding-3-small",
            ),
            EmbeddingCompatibilityState.PROVIDER_MISMATCH,
        ),
        (
            {
                "provider": "supabase",
                "chunks": 0,
                "embeddings": 0,
                "column_type": "not-vector",
                "identities": [],
            },
            EmbeddingCompatibilityState.INVALID_METADATA,
        ),
    ],
)
def test_startup_embedding_health_must_be_ready_or_healthy_empty(
    vector_health: dict[str, Any],
    expected_state: EmbeddingCompatibilityState,
) -> None:
    result = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=_Embedding,
        vector_factory=lambda: _Vector(health=vector_health),
        retrieval_factory=lambda _embedding, _vector: _Retrieval(),
    )

    assert result.bundle is None
    assert result.decision.state is ProviderConfigurationState.STARTUP_HEALTH_FAILED
    assert result.decision.embedding_health_state is expected_state
    assert result.decision.safe_code == "V2_PROVIDER_STARTUP_HEALTH_FAILED"


def test_embedding_health_identity_drift_fails_even_for_empty_index() -> None:
    embedding = _Embedding(
        health=_provider_health(
            provider="openai",
            model="text-embedding-3-small",
        )
    )

    result = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=lambda: embedding,
        vector_factory=_Vector,
        retrieval_factory=lambda _embedding, _vector: _Retrieval(),
    )

    assert result.bundle is None
    assert result.decision.state is ProviderConfigurationState.IMPLEMENTATION_DRIFT
    assert result.decision.actual is not None
    assert result.decision.actual.embedding_provider == "openai"
    assert result.decision.actual.embedding_model == "text-embedding-3-small"
    assert result.decision.embedding_health_state is (
        EmbeddingCompatibilityState.HEALTHY_EMPTY
    )


@pytest.mark.parametrize(
    ("chunks", "expected_state"),
    [
        (0, EmbeddingCompatibilityState.HEALTHY_EMPTY),
        (2, EmbeddingCompatibilityState.READY),
    ],
)
def test_constructs_validated_bundle_for_healthy_runtime(
    chunks: int,
    expected_state: EmbeddingCompatibilityState,
) -> None:
    embedding = _Embedding()
    vector = _Vector(health=_vector_health(chunks=chunks))
    retrieval = _Retrieval()

    result = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=lambda: embedding,
        vector_factory=lambda: vector,
        retrieval_factory=lambda actual_embedding, actual_vector: (
            retrieval
            if (actual_embedding, actual_vector) == (embedding, vector)
            else pytest.fail("Factories were not wired to the retrieval provider")
        ),
    )

    assert result.decision.state is ProviderConfigurationState.VALIDATED
    assert result.decision.embedding_health_state is expected_state
    assert result.bundle is not None
    assert result.bundle.embedding is embedding
    assert result.bundle.vector is vector
    assert result.bundle.retrieval is retrieval
    assert result.bundle.identity == result.decision.declared
    assert result.bundle.embedding_health.state is expected_state


def test_unsupported_configuration_never_constructs_providers() -> None:
    calls: list[str] = []

    result = construct_v2_provider_bundle(
        _configuration(vector_provider="memory"),
        embedding_factory=lambda: calls.append("embedding"),  # type: ignore[arg-type]
        vector_factory=lambda: calls.append("vector"),  # type: ignore[arg-type]
        retrieval_factory=lambda _embedding, _vector: calls.append(  # type: ignore[arg-type]
            "retrieval"
        ),
    )

    assert result.bundle is None
    assert calls == []


def test_construction_failure_is_safe_and_deterministic() -> None:
    def fail() -> _Embedding:
        raise RuntimeError("secret-provider-detail")

    first = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=fail,
    )
    second = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=fail,
    )

    assert first == second
    assert first.bundle is None
    assert first.decision.state is ProviderConfigurationState.CONSTRUCTION_UNAVAILABLE
    assert first.decision.safe_code == "V2_PROVIDER_CONSTRUCTION_UNAVAILABLE"
    assert "secret-provider-detail" not in first.decision.model_dump_json()


def test_default_retrieval_uses_the_validated_runtime_instances() -> None:
    hit = RetrievalHit(
        source="vector",
        document_id=1,
        title="Instrument",
        source_url="https://example.test/instrument",
        text="Evidence",
    )
    embedding = _Embedding()
    vector = _Vector(health=_vector_health(chunks=1), hits=[hit])

    result = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=lambda: embedding,
        vector_factory=lambda: vector,
    )
    assert result.bundle is not None
    assert isinstance(result.bundle.retrieval, SupabaseHybridRetrieval)

    execution = result.bundle.retrieval.branch_search(
        RetrievalBranch.VECTOR,
        "query",
        limit=3,
        event_id=7,
    )

    assert execution.outcome.status is RetrievalBranchStatus.SATISFIED
    assert execution.hits == (hit,)
    assert embedding.embed_calls == ["query"]
    assert vector.search_calls == [(1536, 3, 7)]


def test_v2_retrieval_health_uses_the_validated_runtime_instances() -> None:
    embedding_health = _provider_health()
    vector_health = _vector_health()
    embedding = _Embedding(health=embedding_health)
    vector = _Vector(health=vector_health)

    result = construct_v2_provider_bundle(
        _configuration(),
        embedding_factory=lambda: embedding,
        vector_factory=lambda: vector,
    )
    assert result.bundle is not None

    assert result.bundle.retrieval.health() == {
        "provider": "supabase",
        "vector_store": vector_health,
        "embedding_provider": embedding_health,
    }


def test_legacy_vector_factory_behavior_remains_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from backend.rag import vector_store as vector_store_module

    monkeypatch.setattr(vector_store_module.settings, "vector_provider", "memory")

    assert isinstance(VectorStoreFactory.get_provider(), SupabasePgVectorStore)


def test_configuration_contract_is_strict_frozen_and_canonical() -> None:
    configuration = _configuration()

    with pytest.raises(ValidationError):
        V2ProviderConfiguration(
            **configuration.model_dump(),
            unexpected="value",
        )
    with pytest.raises(ValidationError):
        _configuration(retrieval_provider="SUPABASE")
    with pytest.raises(ValidationError):
        _configuration(embedding_dimension=True)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        configuration.embedding_model = "changed"  # type: ignore[misc]


def test_decision_contract_rejects_inconsistent_health_and_identity() -> None:
    declared = ProviderImplementationIdentity(
        retrieval_provider="supabase",
        vector_provider="supabase",
        embedding_provider="offline",
        embedding_model=OFFLINE_EMBEDDING_MODEL,
        embedding_dimension=1536,
    )

    with pytest.raises(ValidationError):
        ProviderConfigurationDecision(
            policy_version="policy",
            state=ProviderConfigurationState.VALIDATED,
            health=ProviderConfigurationHealth.FAILED,
            declared=declared,
            actual=declared,
            safe_code="FAILURE",
        )
    with pytest.raises(ValidationError):
        ProviderConfigurationDecision(
            policy_version="policy",
            state=ProviderConfigurationState.VALIDATED,
            health=ProviderConfigurationHealth.HEALTHY,
            declared=declared,
            actual=declared.model_copy(
                update={"embedding_model": "other"},
            ),
        )
