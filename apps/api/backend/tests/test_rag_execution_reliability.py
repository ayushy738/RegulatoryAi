"""Phase 4: RAG jobs must be processed after crawl, not left PENDING forever."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.pipeline import run_once
from backend.rag import indexing
from backend.rag.embeddings import OfflineEmbeddingProvider
from backend.rag.models import DocumentChunk


class _InMemoryRagStore:
    """Minimal durable store for claim → index → ready without Postgres."""

    def __init__(self) -> None:
        self.jobs: dict[int, dict[str, Any]] = {}
        self.rag_status: dict[int, dict[str, Any]] = {}
        self.chunks: list[dict[str, Any]] = []
        self.embeddings: list[dict[str, Any]] = []
        self.texts: dict[tuple[int, int | None], dict[str, Any]] = {}
        self._job_seq = 0
        self._chunk_seq = 0
        self._locked_job_ids: set[int] = set()

    def enqueue(self, *, document_id: int, version_id: int | None) -> int:
        existing = next(
            (
                job
                for job in self.jobs.values()
                if job["document_id"] == document_id
                and job.get("version_id") == version_id
            ),
            None,
        )
        if existing:
            if existing["status"] != "COMPLETED":
                existing["status"] = "PENDING"
            job_id = int(existing["job_id"])
        else:
            self._job_seq += 1
            job_id = self._job_seq
            self.jobs[job_id] = {
                "job_id": job_id,
                "document_id": document_id,
                "version_id": version_id,
                "status": "PENDING",
                "attempts": 0,
                "last_error": None,
                "updated_at": datetime.now(UTC),
            }

        prior = self.rag_status.get(document_id)
        if (
            prior
            and prior.get("status") == "RAG_READY"
            and prior.get("version_id") == version_id
        ):
            status = "RAG_READY"
        else:
            status = "PENDING"
        self.rag_status[document_id] = {
            "document_id": document_id,
            "version_id": version_id,
            "status": status,
            "chunk_count": prior.get("chunk_count", 0) if prior else 0,
            "embedded_chunk_count": prior.get("embedded_chunk_count", 0) if prior else 0,
            "error": None,
        }
        return job_id

    def _is_claimable(self, job: dict[str, Any], *, now: datetime) -> bool:
        status = job["status"]
        if status in {"PENDING", "FAILED"}:
            return True
        if status != "PROCESSING":
            return False
        updated_at = job.get("updated_at") or now
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=UTC)
        age = now - updated_at
        return age >= timedelta(seconds=indexing.RAG_PROCESSING_STALE_SECONDS)

    def claim(self, *, limit: int, now: datetime | None = None) -> list[dict[str, Any]]:
        clock = now or datetime.now(UTC)
        candidates = [
            job
            for job in self.jobs.values()
            if int(job["job_id"]) not in self._locked_job_ids
            and self._is_claimable(job, now=clock)
        ]
        candidates.sort(
            key=lambda job: (
                0
                if job["status"] == "PENDING"
                else 1
                if job["status"] == "PROCESSING"
                else 2,
                job["job_id"],
            )
        )
        claimed = candidates[:limit]
        for job in claimed:
            if job["status"] == "PROCESSING":
                job["last_error"] = "Reclaimed after stale PROCESSING timeout."
            job["status"] = "PROCESSING"
            job["attempts"] += 1
            job["updated_at"] = clock
            self._locked_job_ids.add(int(job["job_id"]))
        return [dict(job) for job in claimed]

    def unlock_all(self) -> None:
        self._locked_job_ids.clear()

    def set_text(
        self,
        *,
        document_id: int,
        version_id: int,
        text: str,
        content_hash: str = "hash-1",
        family_id: int | None = 1,
    ) -> None:
        self.texts[(document_id, version_id)] = {
            "document_id": document_id,
            "version_id": version_id,
            "title": f"Doc {document_id}",
            "source_url": f"https://example.gov.in/doc/{document_id}",
            "content_hash": content_hash,
            "text_content": text,
            "family_id": family_id,
        }

    def replace_chunks(self, chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        if not chunks:
            return []
        document_id = chunks[0].document_id
        version_id = chunks[0].version_id
        removed_ids = {
            row["id"]
            for row in self.chunks
            if row["document_id"] == document_id
            and (version_id is None or row.get("version_id") == version_id)
        }
        self.chunks = [row for row in self.chunks if row["id"] not in removed_ids]
        self.embeddings = [
            row for row in self.embeddings if row["chunk_id"] not in removed_ids
        ]
        stored: list[DocumentChunk] = []
        for chunk in chunks:
            self._chunk_seq += 1
            chunk_id = self._chunk_seq
            row = {**chunk.__dict__, "id": chunk_id}
            self.chunks.append(row)
            stored.append(DocumentChunk(**row))
        return stored

    def upsert_embeddings(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> int:
        inserted = 0
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            if chunk.id is None:
                continue
            self.embeddings = [
                row
                for row in self.embeddings
                if not (
                    row["chunk_id"] == chunk.id
                    and row["provider"] == embedding_provider
                    and row["model"] == embedding_model
                )
            ]
            self.embeddings.append(
                {
                    "chunk_id": chunk.id,
                    "provider": embedding_provider,
                    "model": embedding_model,
                    "embedding": embedding,
                    "embedding_dimension": len(embedding),
                }
            )
            inserted += 1
        return inserted

    def update_status(self, **kwargs: Any) -> None:
        document_id = int(kwargs["document_id"])
        self.rag_status[document_id] = {
            "document_id": document_id,
            "version_id": kwargs.get("version_id"),
            "status": kwargs["status"],
            "chunk_count": kwargs.get("chunk_count", 0),
            "embedded_chunk_count": kwargs.get("embedded_chunk_count", 0),
            "error": kwargs.get("error"),
            "provider": kwargs.get("provider"),
            "model": kwargs.get("model"),
        }

    def update_job(self, *, job_id: int, status: str, error: str | None) -> None:
        job = self.jobs[job_id]
        job["status"] = status
        job["last_error"] = error
        job["updated_at"] = datetime.now(UTC)
        self._locked_job_ids.discard(job_id)


def _install_store(monkeypatch: pytest.MonkeyPatch, store: _InMemoryRagStore) -> None:
    def fake_claim(*, limit: int) -> list[dict[str, Any]]:
        return store.claim(limit=limit)

    def fake_load(*, document_id: int, version_id: int | None) -> dict[str, Any] | None:
        if version_id is not None and (document_id, version_id) in store.texts:
            return dict(store.texts[(document_id, version_id)])
        for (doc_id, _ver), row in store.texts.items():
            if doc_id == document_id:
                return dict(row)
        return None

    def fake_replace(chunks: list[DocumentChunk]) -> list[DocumentChunk]:
        return store.replace_chunks(chunks)

    def fake_update_status(**kwargs: Any) -> None:
        store.update_status(**kwargs)

    def fake_record_result(
        result: indexing.RagIndexResult,
        *,
        job_id: int | None,
        provider: str | None = None,
        model: str | None = None,
    ) -> None:
        store.update_status(
            document_id=result.document_id,
            version_id=result.version_id,
            status=result.status,
            chunk_count=result.chunk_count,
            embedded_chunk_count=result.embedded_chunk_count,
            provider=provider,
            model=model,
            error=result.error,
        )
        if job_id is not None:
            store.update_job(
                job_id=job_id,
                status=indexing._job_status(result.status),
                error=result.error,
            )

    class _FakeVectorStore:
        provider_name = "memory"

        def upsert_chunks(
            self,
            chunks: list[DocumentChunk],
            embeddings: list[list[float]],
            *,
            embedding_provider: str,
            embedding_model: str,
        ) -> int:
            return store.upsert_embeddings(
                chunks,
                embeddings,
                embedding_provider=embedding_provider,
                embedding_model=embedding_model,
            )

    monkeypatch.setattr(indexing, "_claim_jobs", fake_claim)
    monkeypatch.setattr(indexing, "_load_document_text", fake_load)
    monkeypatch.setattr(indexing, "_replace_chunks", fake_replace)
    monkeypatch.setattr(indexing, "_update_status", fake_update_status)
    monkeypatch.setattr(indexing, "_record_result", fake_record_result)
    monkeypatch.setattr(
        indexing.EmbeddingProviderFactory,
        "get_provider",
        staticmethod(lambda: OfflineEmbeddingProvider()),
    )
    monkeypatch.setattr(
        indexing.VectorStoreFactory,
        "get_provider",
        staticmethod(lambda: _FakeVectorStore()),
    )


def test_crawl_creates_rag_job_via_enqueue(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _InMemoryRagStore()
    executed: list[str] = []

    def fake_enqueue(session: Any, *, document_id: int, version_id: int | None) -> None:
        executed.append("enqueue")
        store.enqueue(document_id=document_id, version_id=version_id)

    session = MagicMock()
    monkeypatch.setattr(indexing, "enqueue_rag_index_job", fake_enqueue)

    indexing.enqueue_rag_index_job(session, document_id=11, version_id=21)
    # Call through the patched name used by repository too.
    from backend.core import repository

    monkeypatch.setattr(repository, "enqueue_rag_index_job", fake_enqueue)
    repository.enqueue_rag_index_job(session, document_id=11, version_id=21)

    assert executed
    assert any(job["status"] == "PENDING" for job in store.jobs.values())
    assert store.rag_status[11]["status"] == "PENDING"


def test_pending_job_is_processed_to_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _InMemoryRagStore()
    _install_store(monkeypatch, store)
    store.set_text(
        document_id=42,
        version_id=7,
        text=(
            "Central Electricity Regulatory Commission order on grid connectivity. "
            "Transmission licensees shall comply with interconnection standards "
            "and report readiness within ninety days of publication."
        ),
    )
    job_id = store.enqueue(document_id=42, version_id=7)
    assert store.jobs[job_id]["status"] == "PENDING"

    payload = indexing.process_pending_rag_jobs(limit=5)

    assert payload["processed"] == 1
    assert payload["ready"] == 1
    assert payload["failed"] == 0
    assert store.jobs[job_id]["status"] == "COMPLETED"
    assert store.jobs[job_id]["attempts"] == 1
    assert store.rag_status[42]["status"] == "RAG_READY"
    assert store.rag_status[42]["chunk_count"] >= 1
    assert store.rag_status[42]["embedded_chunk_count"] >= 1
    assert store.rag_status[42]["embedded_chunk_count"] == store.rag_status[42]["chunk_count"]
    assert len(store.chunks) >= 1
    assert len(store.embeddings) >= 1
    assert len(store.embeddings) == len(store.chunks)


def test_indexing_failure_is_recorded_and_retryable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _InMemoryRagStore()
    _install_store(monkeypatch, store)
    store.set_text(
        document_id=50,
        version_id=2,
        text="Enough regulatory text for chunking to succeed before embed fails.",
    )
    job_id = store.enqueue(document_id=50, version_id=2)

    class BoomProvider(OfflineEmbeddingProvider):
        def embed_batch(self, texts: list[str]) -> list[list[float]]:
            raise RuntimeError("embedding provider down")

    monkeypatch.setattr(
        indexing.EmbeddingProviderFactory,
        "get_provider",
        staticmethod(lambda: BoomProvider()),
    )

    failed = indexing.process_pending_rag_jobs(limit=1)
    assert failed["processed"] == 1
    assert failed["failed"] == 1
    assert store.jobs[job_id]["status"] == "FAILED"
    assert store.rag_status[50]["status"] == "FAILED"
    assert store.jobs[job_id]["last_error"]
    assert "embedding provider down" in str(store.jobs[job_id]["last_error"])

    # Restore provider; FAILED jobs must be reclaimable.
    monkeypatch.setattr(
        indexing.EmbeddingProviderFactory,
        "get_provider",
        staticmethod(lambda: OfflineEmbeddingProvider()),
    )
    retried = indexing.process_pending_rag_jobs(limit=1)
    assert retried["processed"] == 1
    assert retried["ready"] == 1
    assert store.jobs[job_id]["status"] == "COMPLETED"
    assert store.rag_status[50]["status"] == "RAG_READY"
    assert store.jobs[job_id]["attempts"] >= 2


def test_duplicate_processing_does_not_corrupt_chunks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _InMemoryRagStore()
    _install_store(monkeypatch, store)
    store.set_text(
        document_id=60,
        version_id=3,
        text=(
            "Duplicate indexing must replace prior chunks for the same document "
            "version without leaving orphaned embedding rows for replaced chunk ids."
        ),
    )
    store.enqueue(document_id=60, version_id=3)
    first = indexing.process_pending_rag_jobs(limit=1)
    assert first["ready"] == 1
    first_chunk_ids = {row["id"] for row in store.chunks}
    first_embedding_ids = {row["chunk_id"] for row in store.embeddings}
    assert first_chunk_ids == first_embedding_ids

    # Re-open as PENDING (same version) and process again.
    job = next(iter(store.jobs.values()))
    job["status"] = "PENDING"
    second = indexing.process_pending_rag_jobs(limit=1)
    assert second["ready"] == 1
    second_chunk_ids = {row["id"] for row in store.chunks}
    second_embedding_ids = {row["chunk_id"] for row in store.embeddings}
    assert second_chunk_ids == second_embedding_ids
    # Prior chunk rows for this version were replaced (new ids allowed).
    assert len(store.chunks) == len(second_chunk_ids)
    assert store.rag_status[60]["status"] == "RAG_READY"


def test_enqueue_resets_stale_ready_for_new_version() -> None:
    store = _InMemoryRagStore()
    store.enqueue(document_id=70, version_id=1)
    store.rag_status[70] = {
        "document_id": 70,
        "version_id": 1,
        "status": "RAG_READY",
        "chunk_count": 2,
        "embedded_chunk_count": 2,
        "error": None,
    }
    store.enqueue(document_id=70, version_id=2)
    assert store.rag_status[70]["status"] == "PENDING"
    assert store.rag_status[70]["version_id"] == 2


def test_drain_after_crawl_processes_pending_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _InMemoryRagStore()
    _install_store(monkeypatch, store)
    store.set_text(
        document_id=80,
        version_id=1,
        text=(
            "After crawl persistence, drain_rag_jobs_after_crawl must claim the "
            "pending job and mark the document RAG_READY for retrieval."
        ),
    )
    store.enqueue(document_id=80, version_id=1)

    payload = indexing.drain_rag_jobs_after_crawl(
        extracted_document_count=1,
        run_id=999,
    )

    assert payload is not None
    assert payload["processed"] == 1
    assert payload["ready"] == 1
    assert store.rag_status[80]["status"] == "RAG_READY"
    assert store.chunks
    assert store.embeddings


def test_drain_after_crawl_skips_when_no_documents() -> None:
    assert indexing.drain_rag_jobs_after_crawl(extracted_document_count=0) is None


def test_drain_failure_is_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*, limit: int = 25, include_processing: bool = False) -> dict[str, Any]:
        raise RuntimeError("batch worker crashed")

    monkeypatch.setattr(indexing, "process_pending_rag_jobs", boom)
    assert (
        indexing.drain_rag_jobs_after_crawl(extracted_document_count=3, run_id=1)
        is None
    )


def test_run_crawl_stages_calls_rag_drain_after_persist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order: list[str] = []

    monkeypatch.setattr(
        run_once,
        "list_enabled_source_pages",
        lambda **_: [
            {
                "id": 1,
                "source_id": 2,
                "source_code": "CERC",
                "name": "Orders",
                "url": "https://example.gov.in/orders",
            }
        ],
    )
    monkeypatch.setattr(run_once, "load_checkpoint", lambda *_a, **_k: None)

    async def fake_scrape(_page: Any) -> list[Any]:
        order.append("scrape")
        return []

    monkeypatch.setattr(run_once, "scrape_source_page", fake_scrape)
    monkeypatch.setattr(run_once, "record_discovery_audits", lambda *_a, **_k: None)
    monkeypatch.setattr(run_once, "record_source_check", lambda *_a, **_k: None)

    async def fake_acquire(docs: list[Any], **_k: Any) -> Any:
        order.append("acquire")
        return MagicMock(accepted=[], extracted=[], audits=[], errors=[])

    monkeypatch.setattr(run_once, "acquire_primary_documents", fake_acquire)
    monkeypatch.setattr(
        run_once,
        "persist_extracted_documents",
        lambda docs: order.append(f"persist:{len(docs)}") or [],
    )

    def fake_drain(*, extracted_document_count: int, run_id: int | None = None):
        order.append(f"rag_drain:{extracted_document_count}:{run_id}")
        return {"processed": 0, "ready": 0, "failed": 0, "skipped": 0, "results": []}

    monkeypatch.setattr(run_once, "drain_rag_jobs_after_crawl", fake_drain)
    monkeypatch.setattr(run_once, "mark_source_page_crawled", lambda *_a, **_k: None)
    monkeypatch.setattr(run_once, "save_checkpoint", lambda *_a, **_k: None)
    monkeypatch.setattr(run_once, "build_digest", lambda *_a, **_k: MagicMock(events=[]))
    monkeypatch.setattr(run_once, "enqueue_notifications", lambda *_a, **_k: None)
    monkeypatch.setattr(
        run_once,
        "send_pending_notifications",
        lambda *_a, **_k: MagicMock(message_id=None),
    )
    monkeypatch.setattr(run_once, "finalize_crawl_run", lambda *_a, **_k: None)

    import asyncio

    result = asyncio.run(run_once._run_crawl_stages(55))
    assert "persist:0" in order
    assert "rag_drain:0:55" in order
    assert order.index("persist:0") < order.index("rag_drain:0:55")
    assert result["status"] in {"success", "partial", "failed"}


def test_claim_prefers_pending_over_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    store = _InMemoryRagStore()
    _install_store(monkeypatch, store)
    failed_id = store.enqueue(document_id=1, version_id=1)
    store.jobs[failed_id]["status"] = "FAILED"
    pending_id = store.enqueue(document_id=2, version_id=1)
    store.set_text(document_id=2, version_id=1, text="Pending job should run first. " * 20)

    claimed = indexing._claim_jobs(limit=1)
    assert claimed[0]["job_id"] == pending_id
    assert claimed[0]["document_id"] == 2


def test_fresh_processing_job_is_not_reclaimed() -> None:
    store = _InMemoryRagStore()
    job_id = store.enqueue(document_id=266, version_id=266)
    store.jobs[job_id]["status"] = "PROCESSING"
    store.jobs[job_id]["attempts"] = 1
    store.jobs[job_id]["updated_at"] = datetime.now(UTC)

    claimed = store.claim(limit=10)
    assert claimed == []
    assert store.jobs[job_id]["status"] == "PROCESSING"
    assert store.jobs[job_id]["attempts"] == 1


def test_stale_processing_job_is_reclaimed_and_completed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = _InMemoryRagStore()
    _install_store(monkeypatch, store)
    store.set_text(
        document_id=266,
        version_id=266,
        text=(
            "Orphaned PROCESSING jobs stuck after EMBEDDING must be reclaimed once "
            "updated_at is older than the stale timeout and finish as RAG_READY."
        ),
    )
    job_id = store.enqueue(document_id=266, version_id=266)
    store.jobs[job_id]["status"] = "PROCESSING"
    store.jobs[job_id]["attempts"] = 1
    store.jobs[job_id]["updated_at"] = datetime.now(UTC) - timedelta(
        seconds=indexing.RAG_PROCESSING_STALE_SECONDS + 30
    )
    # Simulate interrupted mid-embed: chunks exist, embeddings missing.
    store.rag_status[266] = {
        "document_id": 266,
        "version_id": 266,
        "status": "EMBEDDING",
        "chunk_count": 14,
        "embedded_chunk_count": 0,
        "error": None,
        "provider": "offline",
        "model": "deterministic-hash-v1",
    }
    store.chunks = [
        {
            "id": i,
            "document_id": 266,
            "version_id": 266,
            "text": f"chunk {i}",
        }
        for i in range(1, 15)
    ]

    payload = indexing.process_pending_rag_jobs(limit=1)

    assert payload["processed"] == 1
    assert payload["ready"] == 1
    assert payload["failed"] == 0
    assert store.jobs[job_id]["status"] == "COMPLETED"
    assert store.jobs[job_id]["attempts"] == 2
    assert store.rag_status[266]["status"] == "RAG_READY"
    assert store.rag_status[266]["chunk_count"] >= 1
    assert (
        store.rag_status[266]["embedded_chunk_count"]
        == store.rag_status[266]["chunk_count"]
    )
    assert len(store.embeddings) == len(store.chunks)


def test_two_workers_cannot_reclaim_same_stale_job() -> None:
    store = _InMemoryRagStore()
    job_id = store.enqueue(document_id=173, version_id=266)
    store.jobs[job_id]["status"] = "PROCESSING"
    store.jobs[job_id]["attempts"] = 1
    store.jobs[job_id]["updated_at"] = datetime.now(UTC) - timedelta(
        seconds=indexing.RAG_PROCESSING_STALE_SECONDS + 60
    )

    first = store.claim(limit=1)
    second = store.claim(limit=1)

    assert len(first) == 1
    assert first[0]["job_id"] == job_id
    assert second == []
    assert store.jobs[job_id]["attempts"] == 2
    assert store.jobs[job_id]["status"] == "PROCESSING"


def test_requeue_processing_only_touches_stale_jobs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stale_id = 173
    captured: dict[str, Any] = {}

    class _Result:
        def __init__(self, rows: list[dict[str, Any]]) -> None:
            self._rows = rows

        def mappings(self) -> "_Result":
            return self

        def all(self) -> list[dict[str, Any]]:
            return self._rows

    class _Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            sql = str(statement)
            captured.setdefault("statements", []).append(sql)
            if "select job_id" in sql.lower():
                captured["select_params"] = params
                assert params is not None
                assert "stale_seconds" in params
                assert "for update skip locked" in sql.lower()
                return _Result([{"job_id": stale_id}])
            captured["update_params"] = params
            return _Result([])

    class _Scope:
        def __enter__(self) -> _Session:
            return _Session()

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(indexing, "session_scope", lambda: _Scope())

    result = indexing.requeue_processing_jobs(limit=10)
    assert result == {"requeued": 1}
    assert (
        captured["select_params"]["stale_seconds"]
        == indexing.RAG_PROCESSING_STALE_SECONDS
    )
    update_sql = captured["statements"][1].lower()
    assert "pending" in update_sql
    assert "stale processing timeout" in update_sql


def test_claim_jobs_sql_reclaims_only_stale_processing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Result:
        def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
            self._rows = rows or []

        def mappings(self) -> "_Result":
            return self

        def all(self) -> list[dict[str, Any]]:
            return self._rows

    class _Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            sql = str(statement)
            captured.setdefault("statements", []).append(sql)
            if "select job_id, document_id, version_id" in sql.lower():
                captured["select_params"] = params
                assert params is not None
                assert "processing" in sql.lower()
                assert "stale_seconds" in params
                assert "for update skip locked" in sql.lower()
                return _Result(
                    [{"job_id": 173, "document_id": 266, "version_id": 266}]
                )
            captured["update_params"] = params
            return _Result([])

    class _Scope:
        def __enter__(self) -> _Session:
            return _Session()

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(indexing, "session_scope", lambda: _Scope())
    rows = indexing._claim_jobs(limit=1)
    assert rows == [{"job_id": 173, "document_id": 266, "version_id": 266}]
    assert (
        captured["select_params"]["stale_seconds"]
        == indexing.RAG_PROCESSING_STALE_SECONDS
    )
    assert "attempts = attempts + 1" in captured["statements"][1].lower()
