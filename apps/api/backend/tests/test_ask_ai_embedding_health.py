from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine

from backend.core.migrations import apply_pending_migrations
from backend.rag import retrieval as retrieval_module
from backend.rag.embedding_health import (
    ConfiguredEmbedding,
    EmbeddingCompatibilityDecision,
    EmbeddingCompatibilityHealth,
    EmbeddingCompatibilityState,
    EmbeddingIdentity,
    EmbeddingIndexObservation,
    IndexedEmbeddingSet,
    evaluate_embedding_compatibility,
    inspect_runtime_embedding_compatibility,
    vector_preflight_outcome,
)
from backend.rag.models import (
    RetrievalBranchHealth,
    RetrievalBranchStatus,
    RetrievalHit,
)
from backend.rag.retrieval import SupabaseHybridRetrieval
from backend.rag.vector_store import SupabasePgVectorStore
from backend.tests.ask_ai_postgres import POSTGRES_MARK

MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"


def _identity(
    *,
    provider: str = "offline",
    model: str = "deterministic-hash-v1",
    dimension: int = 1536,
) -> EmbeddingIdentity:
    return EmbeddingIdentity(
        provider=provider,
        model=model,
        dimension=dimension,
    )


def _configured(
    *,
    identity: EmbeddingIdentity | None = None,
    configured: bool = True,
) -> ConfiguredEmbedding:
    return ConfiguredEmbedding(
        identity=identity or _identity(),
        configured=configured,
    )


def _index(
    *,
    chunks: int = 10,
    sets: tuple[IndexedEmbeddingSet, ...] | None = None,
    column_dimension: int = 1536,
) -> EmbeddingIndexObservation:
    actual_sets = sets
    if actual_sets is None:
        actual_sets = (
            IndexedEmbeddingSet(identity=_identity(), count=chunks),
        ) if chunks else ()
    return EmbeddingIndexObservation(
        chunk_count=chunks,
        embedding_count=sum(item.count for item in actual_sets),
        column_dimension=column_dimension,
        indexed_sets=actual_sets,
    )


class _Health:
    def __init__(
        self,
        value: dict[str, Any] | None = None,
        *,
        error: Exception | None = None,
    ) -> None:
        self.value = value or {}
        self.error = error

    def health(self) -> dict[str, Any]:
        if self.error is not None:
            raise self.error
        return self.value


class _EmbeddingRuntime(_Health):
    def __init__(self, value: dict[str, Any]) -> None:
        super().__init__(value)
        self.embed_calls: list[str] = []

    def embed(self, query: str) -> list[float]:
        self.embed_calls.append(query)
        return [0.1] * 1536


class _VectorRuntime(_Health):
    def __init__(
        self,
        value: dict[str, Any],
        *,
        hits: list[RetrievalHit] | None = None,
    ) -> None:
        super().__init__(value)
        self.hits = hits or []
        self.search_calls: list[tuple[int, int, int | None]] = []

    def similarity_search(
        self,
        embedding: list[float],
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        self.search_calls.append((len(embedding), limit, event_id))
        return self.hits


def _provider_health(
    *,
    provider: str = "offline",
    model: str = "deterministic-hash-v1",
    dimension: int = 1536,
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
    chunks: int,
    identities: list[dict[str, Any]],
    column_type: str = "vector(1536)",
) -> dict[str, Any]:
    return {
        "provider": "supabase",
        "chunks": chunks,
        "embeddings": sum(item["count"] for item in identities),
        "column_type": column_type,
        "identities": identities,
    }


def test_matching_full_index_is_ready_and_queryable() -> None:
    decision = evaluate_embedding_compatibility(
        _configured(),
        _index(),
    )

    assert decision.state is EmbeddingCompatibilityState.READY
    assert decision.health is EmbeddingCompatibilityHealth.HEALTHY
    assert decision.matching_embedding_count == 10
    assert decision.can_query_vector is True
    assert decision.no_match_is_trustworthy is True
    assert decision.safe_code is None
    assert vector_preflight_outcome(decision) is None


def test_compatible_empty_index_is_healthy_no_match() -> None:
    decision = evaluate_embedding_compatibility(
        _configured(),
        _index(chunks=0),
    )
    outcome = vector_preflight_outcome(decision)

    assert decision.state is EmbeddingCompatibilityState.HEALTHY_EMPTY
    assert decision.can_query_vector is False
    assert decision.no_match_is_trustworthy is True
    assert outcome is not None
    assert outcome.status is RetrievalBranchStatus.NO_MATCH
    assert outcome.health is RetrievalBranchHealth.HEALTHY
    assert outcome.safe_failure_code is None


def test_chunks_without_embeddings_are_partial_not_empty() -> None:
    decision = evaluate_embedding_compatibility(
        _configured(),
        _index(chunks=5, sets=()),
    )
    outcome = vector_preflight_outcome(decision)

    assert decision.state is EmbeddingCompatibilityState.PARTIAL_INDEX
    assert decision.health is EmbeddingCompatibilityHealth.DEGRADED
    assert decision.no_match_is_trustworthy is False
    assert decision.safe_code == "EMBEDDING_INDEX_PARTIAL"
    assert outcome is not None
    assert outcome.status is RetrievalBranchStatus.PARTIAL
    assert outcome.match_count == 0


def test_partially_matching_index_is_queryable_but_no_match_is_untrusted() -> None:
    decision = evaluate_embedding_compatibility(
        _configured(),
        _index(
            chunks=10,
            sets=(
                IndexedEmbeddingSet(identity=_identity(), count=7),
            ),
        ),
    )

    assert decision.state is EmbeddingCompatibilityState.PARTIAL_INDEX
    assert decision.matching_embedding_count == 7
    assert decision.can_query_vector is True
    assert decision.no_match_is_trustworthy is False


def test_stale_other_identity_does_not_hide_complete_matching_index() -> None:
    decision = evaluate_embedding_compatibility(
        _configured(),
        _index(
            chunks=10,
            sets=(
                IndexedEmbeddingSet(identity=_identity(), count=10),
                IndexedEmbeddingSet(
                    identity=_identity(model="old-model"),
                    count=4,
                ),
            ),
        ),
    )

    assert decision.state is EmbeddingCompatibilityState.READY
    assert decision.embedding_count == 14
    assert decision.matching_embedding_count == 10


@pytest.mark.parametrize(
    ("configured", "index", "state", "safe_code"),
    (
        (
            _configured(configured=False),
            _index(),
            EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE,
            "EMBEDDING_PROVIDER_UNAVAILABLE",
        ),
        (
            _configured(),
            _index(
                sets=(
                    IndexedEmbeddingSet(
                        identity=_identity(provider="openai"),
                        count=10,
                    ),
                )
            ),
            EmbeddingCompatibilityState.PROVIDER_MISMATCH,
            "EMBEDDING_PROVIDER_MISMATCH",
        ),
        (
            _configured(),
            _index(
                sets=(
                    IndexedEmbeddingSet(
                        identity=_identity(model="old-model"),
                        count=10,
                    ),
                )
            ),
            EmbeddingCompatibilityState.MODEL_MISMATCH,
            "EMBEDDING_MODEL_MISMATCH",
        ),
        (
            _configured(),
            _index(
                sets=(
                    IndexedEmbeddingSet(
                        identity=_identity(dimension=768),
                        count=10,
                    ),
                )
            ),
            EmbeddingCompatibilityState.DIMENSION_MISMATCH,
            "EMBEDDING_DIMENSION_MISMATCH",
        ),
        (
            _configured(identity=_identity(dimension=768)),
            _index(chunks=0, column_dimension=1536),
            EmbeddingCompatibilityState.DIMENSION_MISMATCH,
            "EMBEDDING_DIMENSION_MISMATCH",
        ),
    ),
)
def test_incompatibility_is_explicit_and_never_no_match(
    configured: ConfiguredEmbedding,
    index: EmbeddingIndexObservation,
    state: EmbeddingCompatibilityState,
    safe_code: str,
) -> None:
    decision = evaluate_embedding_compatibility(configured, index)
    outcome = vector_preflight_outcome(decision)

    assert decision.state is state
    assert decision.health is EmbeddingCompatibilityHealth.FAILED
    assert decision.no_match_is_trustworthy is False
    assert decision.safe_code == safe_code
    assert outcome is not None
    assert outcome.status in {
        RetrievalBranchStatus.UNAVAILABLE,
        RetrievalBranchStatus.INVALID_OUTPUT,
    }
    assert outcome.status is not RetrievalBranchStatus.NO_MATCH


def test_runtime_health_reads_grouped_identity_and_physical_dimension() -> None:
    decision = inspect_runtime_embedding_compatibility(
        _Health(_provider_health()),
        _Health(
            _vector_health(
                chunks=2,
                identities=[
                    {
                        "provider": "offline",
                        "model": "deterministic-hash-v1",
                        "dimension": 1536,
                        "count": 2,
                    }
                ],
            )
        ),
    )

    assert decision.state is EmbeddingCompatibilityState.READY
    assert decision.configured_identity == _identity()


def test_runtime_startup_provider_and_index_failures_are_safe() -> None:
    provider_failure = inspect_runtime_embedding_compatibility(
        _Health(error=RuntimeError("secret provider detail")),
        _Health({}),
    )
    index_failure = inspect_runtime_embedding_compatibility(
        _Health(_provider_health()),
        _Health(error=RuntimeError("secret database detail")),
    )

    assert provider_failure.state is EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE
    assert provider_failure.safe_code == "EMBEDDING_PROVIDER_UNAVAILABLE"
    assert index_failure.state is EmbeddingCompatibilityState.METADATA_UNAVAILABLE
    assert index_failure.safe_code == "EMBEDDING_INDEX_METADATA_UNAVAILABLE"
    assert "secret" not in provider_failure.model_dump_json()
    assert "secret" not in index_failure.model_dump_json()


def test_unconfigured_provider_precedes_unavailable_index_metadata() -> None:
    decision = inspect_runtime_embedding_compatibility(
        _Health(_provider_health(configured=False)),
        _Health(error=RuntimeError("database also unavailable")),
    )

    assert decision.state is EmbeddingCompatibilityState.PROVIDER_UNAVAILABLE
    assert decision.configured_identity == _identity()
    assert decision.safe_code == "EMBEDDING_PROVIDER_UNAVAILABLE"


@pytest.mark.parametrize(
    ("vector_health", "expected_status", "expected_code"),
    (
        (
            _vector_health(chunks=0, identities=[]),
            RetrievalBranchStatus.NO_MATCH,
            None,
        ),
        (
            _vector_health(
                chunks=2,
                identities=[
                    {
                        "provider": "openai",
                        "model": "deterministic-hash-v1",
                        "dimension": 1536,
                        "count": 2,
                    }
                ],
            ),
            RetrievalBranchStatus.INVALID_OUTPUT,
            "EMBEDDING_PROVIDER_MISMATCH",
        ),
        (
            _vector_health(chunks=2, identities=[]),
            RetrievalBranchStatus.PARTIAL,
            "EMBEDDING_INDEX_PARTIAL",
        ),
    ),
)
def test_real_vector_branch_preflight_never_collapses_incompatibility_to_no_match(
    monkeypatch: pytest.MonkeyPatch,
    vector_health: dict[str, Any],
    expected_status: RetrievalBranchStatus,
    expected_code: str | None,
) -> None:
    embedding = _EmbeddingRuntime(_provider_health())
    vector = _VectorRuntime(vector_health)
    monkeypatch.setattr(
        retrieval_module.EmbeddingProviderFactory,
        "get_provider",
        lambda: embedding,
    )
    monkeypatch.setattr(
        retrieval_module.VectorStoreFactory,
        "get_provider",
        lambda: vector,
    )

    execution = SupabaseHybridRetrieval().branch_search(
        retrieval_module.RetrievalBranch.VECTOR,
        "question",
        limit=5,
        event_id=7,
    )

    assert execution.outcome.status is expected_status
    assert execution.outcome.safe_failure_code == expected_code
    assert embedding.embed_calls == []
    assert vector.search_calls == []


def test_real_vector_branch_queries_only_after_ready_preflight(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    embedding = _EmbeddingRuntime(_provider_health())
    hit = RetrievalHit(
        source="vector",
        document_id=1,
        title="Official document",
        source_url="https://official.example/1",
        text="Evidence",
        vector_score=0.9,
    )
    vector = _VectorRuntime(
        _vector_health(
            chunks=1,
            identities=[
                {
                    "provider": "offline",
                    "model": "deterministic-hash-v1",
                    "dimension": 1536,
                    "count": 1,
                }
            ],
        ),
        hits=[hit],
    )
    monkeypatch.setattr(
        retrieval_module.EmbeddingProviderFactory,
        "get_provider",
        lambda: embedding,
    )
    monkeypatch.setattr(
        retrieval_module.VectorStoreFactory,
        "get_provider",
        lambda: vector,
    )

    execution = SupabaseHybridRetrieval().branch_search(
        retrieval_module.RetrievalBranch.VECTOR,
        "question",
        limit=5,
        event_id=7,
    )

    assert execution.outcome.status is RetrievalBranchStatus.SATISFIED
    assert execution.hits == (hit,)
    assert embedding.embed_calls == ["question"]
    assert vector.search_calls == [(1536, 5, 7)]


def test_vector_factory_failure_is_safe_and_legacy_public_method_stays_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail() -> None:
        raise RuntimeError("secret configuration detail")

    monkeypatch.setattr(
        retrieval_module.EmbeddingProviderFactory,
        "get_provider",
        fail,
    )
    provider = SupabaseHybridRetrieval()

    execution = provider.branch_search(
        retrieval_module.RetrievalBranch.VECTOR,
        "question",
        limit=5,
    )
    legacy = provider.vector_search("question", limit=5)

    assert execution.outcome.status is RetrievalBranchStatus.UNAVAILABLE
    assert (
        execution.outcome.safe_failure_code
        == "EMBEDDING_PROVIDER_UNAVAILABLE"
    )
    assert "secret" not in execution.outcome.model_dump_json()
    assert legacy == []


@pytest.mark.parametrize(
    ("provider_health", "vector_health"),
    (
        ({"provider": "offline"}, {}),
        (
            _provider_health(),
            _vector_health(chunks=0, identities=[], column_type="vector"),
        ),
        (
            _provider_health(),
            {
                **_vector_health(chunks=1, identities=[]),
                "embeddings": 1,
            },
        ),
        (
            _provider_health(),
            {
                **_vector_health(chunks=1, identities=[]),
                "identities": ["malformed"],
            },
        ),
    ),
)
def test_runtime_malformed_metadata_fails_closed(
    provider_health: dict[str, Any],
    vector_health: dict[str, Any],
) -> None:
    decision = inspect_runtime_embedding_compatibility(
        _Health(provider_health),
        _Health(vector_health),
    )

    assert decision.state is EmbeddingCompatibilityState.INVALID_METADATA
    assert decision.safe_code == "EMBEDDING_HEALTH_INVALID_METADATA"
    assert decision.no_match_is_trustworthy is False
    assert vector_preflight_outcome(decision).status is RetrievalBranchStatus.INVALID_OUTPUT  # type: ignore[union-attr]


def test_inventory_contract_rejects_duplicates_counts_and_orphans() -> None:
    entry = IndexedEmbeddingSet(identity=_identity(), count=1)
    with pytest.raises(ValidationError, match="unique"):
        EmbeddingIndexObservation(
            chunk_count=1,
            embedding_count=2,
            column_dimension=1536,
            indexed_sets=(entry, entry),
        )
    with pytest.raises(ValidationError, match="count"):
        EmbeddingIndexObservation(
            chunk_count=2,
            embedding_count=2,
            column_dimension=1536,
            indexed_sets=(entry,),
        )
    with pytest.raises(ValidationError, match="without chunks"):
        EmbeddingIndexObservation(
            chunk_count=0,
            embedding_count=1,
            column_dimension=1536,
            indexed_sets=(entry,),
        )


def test_decision_contract_rejects_health_query_and_no_match_drift() -> None:
    decision = evaluate_embedding_compatibility(
        _configured(),
        _index(),
    )
    for update in (
        {"health": EmbeddingCompatibilityHealth.FAILED},
        {"can_query_vector": False},
        {"no_match_is_trustworthy": False},
        {"safe_code": "SHOULD_NOT_EXIST"},
    ):
        with pytest.raises(ValidationError):
            EmbeddingCompatibilityDecision(
                **{**decision.model_dump(), **update}
            )


def test_compatibility_is_deterministic_strict_and_immutable() -> None:
    configured = _configured()
    index = _index()
    first = evaluate_embedding_compatibility(configured, index)
    second = evaluate_embedding_compatibility(configured, index)

    assert first == second
    assert first.model_dump_json() == second.model_dump_json()
    with pytest.raises(ValidationError):
        EmbeddingCompatibilityDecision.model_validate(
            {**first.model_dump(), "extra": "forbidden"}
        )


@POSTGRES_MARK
def test_vector_store_health_reads_empty_and_grouped_physical_inventory(
    postgres_engine: Engine,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    apply_pending_migrations(
        postgres_engine,
        MIGRATIONS_DIR,
        through="0014",
    )

    @contextmanager
    def scoped_session() -> Iterator[Connection]:
        with postgres_engine.begin() as connection:
            yield connection

    monkeypatch.setattr(
        "backend.rag.vector_store.session_scope",
        scoped_session,
    )
    store = SupabasePgVectorStore()

    empty = store.health()

    assert empty["chunks"] == 0
    assert empty["embeddings"] == 0
    assert empty["column_type"] == "vector(1536)"
    assert empty["identities"] == []

    vector = "[" + ",".join(("1", *("0" for _ in range(1535)))) + "]"
    with postgres_engine.begin() as connection:
        source_id = connection.execute(
            text(
                """
                insert into sources (
                  code, name, jurisdiction, url, crawler_type
                )
                values ('TEST', 'Test', 'central', 'https://official.example', 'static')
                returning id
                """
            )
        ).scalar_one()
        document_id = connection.execute(
            text(
                """
                insert into documents (
                  source_id, url_hash, source_url, title
                )
                values (
                  :source_id, 'hash-1', 'https://official.example/doc', 'Document'
                )
                returning id
                """
            ),
            {"source_id": source_id},
        ).scalar_one()
        version_id = connection.execute(
            text(
                """
                insert into document_versions (
                  document_id, file_hash, content_hash
                )
                values (:document_id, 'file-1', 'content-1')
                returning id
                """
            ),
            {"document_id": document_id},
        ).scalar_one()
        chunk_id = connection.execute(
            text(
                """
                insert into document_chunks (
                  document_id, version_id, chunk_index, text, token_count
                )
                values (:document_id, :version_id, 0, 'Evidence', 1)
                returning id
                """
            ),
            {"document_id": document_id, "version_id": version_id},
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into document_chunk_embeddings (
                  chunk_id, provider, model, embedding, embedding_dimension
                )
                values (
                  :chunk_id,
                  'offline',
                  'deterministic-hash-v1',
                  cast(:embedding as vector),
                  1536
                )
                """
            ),
            {"chunk_id": chunk_id, "embedding": vector},
        )

    populated = store.health()

    assert populated["chunks"] == 1
    assert populated["embeddings"] == 1
    assert populated["identities"] == [
        {
            "provider": "offline",
            "model": "deterministic-hash-v1",
            "dimension": 1536,
            "count": 1,
        }
    ]
