from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from sqlalchemy import text

from backend.core.config import settings
from backend.core.db import session_scope
from backend.rag.models import DocumentChunk, RetrievalHit


class VectorStore(ABC):
    provider_name: str

    @abstractmethod
    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def delete_document(self, document_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        raise NotImplementedError

    @abstractmethod
    def health(self) -> dict[str, Any]:
        raise NotImplementedError


class SupabasePgVectorStore(VectorStore):
    provider_name = "supabase"

    def upsert_chunks(
        self,
        chunks: list[DocumentChunk],
        embeddings: list[list[float]],
        *,
        embedding_provider: str,
        embedding_model: str,
    ) -> int:
        if len(chunks) != len(embeddings):
            raise ValueError("Chunk and embedding counts must match.")
        inserted = 0
        with session_scope() as session:
            for chunk, embedding in zip(chunks, embeddings, strict=True):
                if chunk.id is None:
                    continue
                session.execute(
                    text(
                        """
                        insert into document_chunk_embeddings (
                          chunk_id,
                          provider,
                          model,
                          embedding,
                          embedding_dimension,
                          updated_at
                        )
                        values (
                          :chunk_id,
                          :provider,
                          :model,
                          cast(:embedding as vector),
                          :embedding_dimension,
                          now()
                        )
                        on conflict (chunk_id, provider, model) do update set
                          embedding = excluded.embedding,
                          embedding_dimension = excluded.embedding_dimension,
                          updated_at = now()
                        """
                    ),
                    {
                        "chunk_id": chunk.id,
                        "provider": embedding_provider,
                        "model": embedding_model,
                        "embedding": _vector_literal(embedding),
                        "embedding_dimension": len(embedding),
                    },
                )
                inserted += 1
        return inserted

    def delete_document(self, document_id: int) -> None:
        with session_scope() as session:
            session.execute(
                text("delete from document_chunks where document_id = :document_id"),
                {"document_id": document_id},
            )

    def similarity_search(
        self,
        query_embedding: list[float],
        *,
        limit: int,
        event_id: int | None = None,
    ) -> list[RetrievalHit]:
        event_join = ""
        event_clause = ""
        params: dict[str, Any] = {
            "embedding": _vector_literal(query_embedding),
            "provider": settings.embedding_provider,
            "model": _embedding_model_for_query(),
            "limit": limit,
        }
        if event_id is not None:
            event_join = "join events ev on ev.document_id = d.id"
            event_clause = "and ev.id = :event_id"
            params["event_id"] = event_id
        query = text(
            f"""
            select
              c.id as chunk_id,
              c.document_id,
              c.version_id,
              c.family_id,
              c.chunk_index,
              c.page_number,
              c.section_title,
              c.text as chunk_text,
              d.title,
              d.issuing_body,
              d.issue_date,
              d.source_url,
              1 - (e.embedding <=> cast(:embedding as vector)) as vector_score
            from document_chunk_embeddings e
            join document_chunks c on c.id = e.chunk_id
            join documents d on d.id = c.document_id
            {event_join}
            where e.provider = :provider
              and e.model = :model
              {event_clause}
            order by e.embedding <=> cast(:embedding as vector)
            limit :limit
            """
        )
        with session_scope() as session:
            rows = session.execute(query, params).mappings()
            return [_hit_from_row(row) for row in rows]

    def health(self) -> dict[str, Any]:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select
                      (select count(*) from document_chunks) as chunks,
                      (select count(*) from document_chunk_embeddings) as embeddings
                    """
                )
            ).mappings().first()
            return {
                "provider": self.provider_name,
                "chunks": int(row["chunks"] if row else 0),
                "embeddings": int(row["embeddings"] if row else 0),
            }


class VectorStoreFactory:
    @staticmethod
    def get_provider() -> VectorStore:
        return SupabasePgVectorStore()


def _hit_from_row(row: Any) -> RetrievalHit:
    return RetrievalHit(
        source="vector",
        document_id=int(row["document_id"]),
        title=row["title"],
        issuer=row["issuing_body"],
        issue_date=row["issue_date"],
        source_url=row["source_url"],
        version_id=row["version_id"],
        family_id=row["family_id"],
        chunk_id=row["chunk_id"],
        chunk_index=row["chunk_index"],
        page_number=row["page_number"],
        section_title=row["section_title"],
        text=row["chunk_text"],
        vector_score=float(row["vector_score"] or 0),
    )


def _embedding_model_for_query() -> str:
    if settings.embedding_provider == "offline":
        return "deterministic-hash-v1"
    return settings.embedding_model


def _vector_literal(values: list[float]) -> str:
    return "[" + ",".join(f"{value:.8f}" for value in values) + "]"
