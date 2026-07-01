from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.core.config import settings
from backend.core.db import session_scope
from backend.rag.models import Citation, RetrievalHit, citation_to_dict, hit_to_dict


def record_chat_retrieval_audit(
    *,
    user_id: str,
    event_id: int | None,
    question: str,
    detected_intent: str,
    retrieval_provider: str,
    retrieved_chunks: list[RetrievalHit],
    graph_entities: list[RetrievalHit],
    citations: list[Citation],
    related_questions: list[str],
    model: str,
    response_latency_ms: int,
    retrieval_latency_ms: int,
    context_tokens: int,
) -> None:
    try:
        with session_scope() as session:
            session.execute(
                text(
                    """
                    insert into chat_retrieval_audit (
                      user_id,
                      event_id,
                      question,
                      detected_intent,
                      retrieval_provider,
                      embedding_provider,
                      vector_provider,
                      retrieved_chunks,
                      graph_entities,
                      citations,
                      related_questions,
                      model,
                      response_latency_ms,
                      retrieval_latency_ms,
                      context_tokens
                    )
                    values (
                      :user_id,
                      :event_id,
                      :question,
                      :detected_intent,
                      :retrieval_provider,
                      :embedding_provider,
                      :vector_provider,
                      cast(:retrieved_chunks as jsonb),
                      cast(:graph_entities as jsonb),
                      cast(:citations as jsonb),
                      cast(:related_questions as jsonb),
                      :model,
                      :response_latency_ms,
                      :retrieval_latency_ms,
                      :context_tokens
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "event_id": event_id,
                    "question": question,
                    "detected_intent": detected_intent,
                    "retrieval_provider": retrieval_provider,
                    "embedding_provider": settings.embedding_provider,
                    "vector_provider": settings.vector_provider,
                    "retrieved_chunks": json.dumps(
                        [hit_to_dict(hit) for hit in retrieved_chunks],
                        default=str,
                    ),
                    "graph_entities": json.dumps(
                        [hit_to_dict(hit) for hit in graph_entities],
                        default=str,
                    ),
                    "citations": json.dumps(
                        [citation_to_dict(citation) for citation in citations],
                        default=str,
                    ),
                    "related_questions": json.dumps(related_questions),
                    "model": model,
                    "response_latency_ms": response_latency_ms,
                    "retrieval_latency_ms": retrieval_latency_ms,
                    "context_tokens": context_tokens,
                },
            )
    except SQLAlchemyError:
        return
