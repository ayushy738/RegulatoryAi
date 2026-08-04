from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from backend.ask.decision.shadow import DecisionShadowService
from backend.core.config import settings
from backend.core.db import session_scope
from backend.core.llm import get_llm_client
from backend.core.logging import configure_logging, log_event
from backend.pipeline.run_once import run_crawl
from backend.rag.context_builder import build_context
from backend.rag.indexing import process_pending_rag_jobs
from backend.rag.retrieval import RetrievalProviderFactory

SYSTEM_PROMPT = (
    "You are a regulatory analyst assistant for India's energy sector. "
    "Answer using only the retrieved evidence. Include citations for factual claims. "
    "If the evidence is insufficient, say so clearly."
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run the P0 crawl-to-grounded-answer acceptance path."
    )
    parser.add_argument("--source-id", type=int, default=None)
    parser.add_argument("--page-id", type=int, default=None)
    parser.add_argument("--query", default="What is DSM?")
    parser.add_argument("--rag-job-limit", type=int, default=25)
    args = parser.parse_args()

    configure_logging()
    try:
        result = asyncio.run(_run_acceptance(args))
    except AcceptanceFailure as exc:
        log_event("p0_acceptance_failed", stage_name=exc.stage, error=str(exc))
        raise SystemExit(f"P0 acceptance failed at {exc.stage}: {exc}") from exc
    print(json.dumps(result, indent=2, default=str))


async def _run_acceptance(args: argparse.Namespace) -> dict[str, Any]:
    log_event(
        "p0_acceptance_started",
        source_id=args.source_id,
        source_page_id=args.page_id,
        query=args.query,
    )

    before = _snapshot()
    _require_database_reachable(before)

    log_event("p0_crawl_stage_started")
    crawl_result = await run_crawl(source_id=args.source_id, page_id=args.page_id)
    log_event("p0_crawl_stage_finished", **_flatten_crawl_result(crawl_result))
    if crawl_result.get("status") not in {"success", "partial"}:
        raise AcceptanceFailure("crawl", crawl_result.get("errors") or crawl_result)
    if int(crawl_result.get("docs_found") or 0) < 1:
        raise AcceptanceFailure("crawl", "Crawler completed without discovering a document.")
    if int(crawl_result.get("primary_docs_found") or 0) < 1:
        raise AcceptanceFailure(
            "document_acquisition",
            "Crawler did not acquire a primary document.",
        )

    after_crawl = _snapshot()
    if after_crawl["documents"] < 1:
        raise AcceptanceFailure("document_persistence", "No documents are persisted.")
    log_event(
        "p0_document_persistence_verified",
        documents_before=before["documents"],
        documents_after=after_crawl["documents"],
        document_texts=after_crawl["document_texts"],
    )

    if after_crawl["entity_catalog"] < 1:
        raise AcceptanceFailure(
            "entity_catalog",
            "Entity catalog is empty after crawl and graph extraction.",
        )
    log_event(
        "p0_entity_catalog_verified",
        entity_catalog_entries=after_crawl["entity_catalog"],
        entity_aliases=after_crawl["entity_aliases"],
    )

    log_event("p0_rag_index_stage_started", limit=args.rag_job_limit)
    rag_result = process_pending_rag_jobs(
        limit=args.rag_job_limit,
        include_processing=True,
    )
    after_rag = _snapshot()
    log_event(
        "p0_rag_index_stage_finished",
        processed=rag_result["processed"],
        ready=rag_result["ready"],
        failed=rag_result["failed"],
        document_chunks=after_rag["document_chunks"],
        chunk_embeddings=after_rag["chunk_embeddings"],
    )
    if after_rag["document_chunks"] < 1:
        raise AcceptanceFailure("rag_index", "No document chunks are available.")

    log_event("p0_retrieval_stage_started", query=args.query)
    retrieval = RetrievalProviderFactory.get_provider().hybrid_search(
        args.query,
        limit=settings.rag_top_k,
    )
    context = build_context(retrieval)
    log_event(
        "p0_retrieval_stage_finished",
        hits=len(retrieval.hits),
        citations=len(context.citations),
        graph_facts=len(context.graph_facts),
        intent=retrieval.intent.name,
    )
    if not retrieval.hits or not context.citations:
        raise AcceptanceFailure(
            "retrieval",
            "Retrieval returned no citation-backed evidence.",
        )

    model = settings.llm_model_chat or "offline-demo"
    log_event("p0_llm_stage_started", model=model, citations=len(context.citations))
    reply = get_llm_client().complete_text(
        system=SYSTEM_PROMPT,
        user=(
            f"Retrieved context:\n{context.prompt_context}\n\n"
            f"Question:\n{args.query}\n\n"
            "Return a grounded answer with citations."
        ),
        model=model,
    )
    log_event("p0_llm_stage_finished", model=model, reply_length=len(reply))
    if not reply.strip():
        raise AcceptanceFailure("llm", "LLM returned an empty response.")

    log_event("p0_decision_shadow_stage_started", intent=retrieval.intent.name)
    decision = DecisionShadowService().evaluate_and_record(
        query=args.query,
        legacy_intent=retrieval.intent.name,  # type: ignore[arg-type]
    )
    log_event(
        "p0_decision_shadow_stage_finished",
        outcome=decision.comparison.outcome.value,
        shadow_intent=(
            decision.comparison.shadow_intent.value
            if decision.comparison.shadow_intent is not None
            else None
        ),
    )
    if decision.decision_record is None:
        raise AcceptanceFailure(
            "decision_shadow",
            decision.comparison.safe_error_code or "Decision shadow unavailable.",
        )

    log_event(
        "p0_grounded_answer_verified",
        citations=len(context.citations),
        model=model,
        intent=retrieval.intent.name,
    )
    result = {
        "status": "passed",
        "crawl": crawl_result,
        "rag_index": rag_result,
        "retrieval": {
            "hits": len(retrieval.hits),
            "citations": len(context.citations),
            "graph_facts": len(context.graph_facts),
            "intent": retrieval.intent.name,
        },
        "llm": {"model": model, "reply_length": len(reply)},
        "decision_shadow": {
            "outcome": decision.comparison.outcome.value,
            "shadow_intent": (
                decision.comparison.shadow_intent.value
                if decision.comparison.shadow_intent is not None
                else None
            ),
        },
    }
    log_event("p0_acceptance_passed", **result["retrieval"], model=model)
    return result


def _snapshot() -> dict[str, int]:
    try:
        with session_scope() as session:
            row = session.execute(
                text(
                    """
                    select
                      (select count(*) from documents) as documents,
                      (select count(*) from document_texts) as document_texts,
                      (select count(*) from public.regulatory_entity_catalog) as entity_catalog,
                      (select count(*) from public.regulatory_entity_aliases) as entity_aliases,
                      (select count(*) from document_chunks) as document_chunks,
                      (select count(*) from document_chunk_embeddings) as chunk_embeddings
                    """
                )
            ).mappings().one()
    except SQLAlchemyError as exc:
        raise AcceptanceFailure("database", f"{type(exc).__name__}: {exc}") from exc
    except Exception as exc:
        raise AcceptanceFailure("database", f"{type(exc).__name__}: {exc}") from exc
    return {key: int(value or 0) for key, value in row.items()}


def _require_database_reachable(snapshot: dict[str, int]) -> None:
    log_event("p0_database_verified", **snapshot)


def _flatten_crawl_result(crawl_result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": crawl_result.get("status"),
        "sources_attempted": crawl_result.get("sources_attempted"),
        "pages_attempted": crawl_result.get("pages_attempted"),
        "sources_succeeded": crawl_result.get("sources_succeeded"),
        "pages_succeeded": crawl_result.get("pages_succeeded"),
        "docs_found": crawl_result.get("docs_found"),
        "primary_docs_found": crawl_result.get("primary_docs_found"),
        "new_events": crawl_result.get("new_events"),
        "checkpoints_advanced": crawl_result.get("checkpoints_advanced"),
        "error_count": len(crawl_result.get("errors") or []),
    }


class AcceptanceFailure(RuntimeError):
    def __init__(self, stage: str, detail: Any) -> None:
        self.stage = stage
        super().__init__(str(detail))


if __name__ == "__main__":
    main()
