import time
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from fastapi.responses import JSONResponse

from backend.api.ask_errors import safe_ask_error
from backend.api.ask_metrics import AskMetrics
from backend.api.deps import UserDep
from backend.api.ratelimit import limit_chat
from backend.ask.decision.shadow import (
    DecisionShadowService,
    LoggingShadowComparisonRecorder,
)
from backend.core.config import settings
from backend.core.llm import get_llm_client
from backend.core.models import ChatRequest, ChatResponse
from backend.core.repository import chat_history as get_chat_history
from backend.core.repository import save_chat_message
from backend.rag.audit import record_chat_retrieval_audit
from backend.rag.context_builder import build_context
from backend.rag.models import BuiltContext, IntentName, citation_to_dict
from backend.rag.retrieval import RetrievalProviderFactory

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are a regulatory analyst assistant for India's energy sector. "
    "Answer using ONLY the retrieved evidence and knowledge graph facts. "
    "Every factual claim must be grounded in the citation inventory. Include concise "
    "citations with document title, issuer, issue date, source URL, and chunk/page "
    "when available. If evidence is insufficient, say so clearly. Distinguish fact "
    "from inference. Do not invent obligations, deadlines, amendments, stakeholders, "
    "or relationships."
)


@router.post("", response_model=ChatResponse, dependencies=[Depends(limit_chat)])
async def chat(
    request: ChatRequest,
    user: UserDep,
    http_request: Request,
    background_tasks: BackgroundTasks,
) -> ChatResponse | JSONResponse:
    started = time.perf_counter()
    metrics = AskMetrics(http_request)
    metrics.record("auth", "success", metrics.request_started)
    model = settings.llm_model_chat or "offline-demo"
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in reversed(get_chat_history(user.id, request.event_id)[-8:])
    ]
    persistence_started = metrics.start()
    user_persisted = save_chat_message(user.id, "user", request.message, request.event_id)
    metrics.record(
        "user_persistence",
        "suppressed_failure" if user_persisted is False else "success",
        persistence_started,
    )

    retrieval_provider = RetrievalProviderFactory.get_provider()
    retrieval_started = metrics.start()
    try:
        retrieval = retrieval_provider.hybrid_search(
            request.message,
            limit=settings.rag_top_k,
            event_id=request.event_id,
        )
    except Exception as exc:
        metrics.record("retrieval", "unavailable", retrieval_started)
        metrics.finish("unavailable")
        return safe_ask_error(
            http_request,
            status_code=500,
            code="RETRIEVAL_UNAVAILABLE",
            detail="Regulatory evidence retrieval is temporarily unavailable.",
            internal_detail=f"{type(exc).__name__}: {exc}",
        )
    metrics.record(
        "retrieval",
        "success" if retrieval.hits else "no_match",
        retrieval_started,
    )
    _schedule_decision_shadow(
        background_tasks=background_tasks,
        metrics=metrics,
        query=request.message,
        legacy_intent=retrieval.intent.name,
    )
    context = build_context(retrieval)
    if not context.citations:
        metrics.record("model", "skipped", metrics.start())
        reply = (
            "I do not have enough retrieved evidence to answer this from the regulatory "
            "corpus. No citation-backed chunks or graph facts were found for this question."
        )
        persistence_started = metrics.start()
        assistant_persisted = save_chat_message(
            user.id,
            "assistant",
            reply,
            request.event_id,
        )
        metrics.record(
            "assistant_persistence",
            "suppressed_failure" if assistant_persisted is False else "success",
            persistence_started,
        )
        _record_audit(
            user_id=user.id,
            event_id=request.event_id,
            question=request.message,
            model=model,
            retrieval_provider=retrieval_provider.provider_name,
            context=context,
            retrieval=retrieval,
            started=started,
        )
        metrics.finish("no_match")
        return ChatResponse(
            reply=reply,
            event_id=request.event_id,
            model=model,
            intent=retrieval.intent.name,
            citations=[],
            related_questions=context.related_questions,
        )

    model_started = metrics.start()
    try:
        reply = get_llm_client().complete_text(
            system=SYSTEM_PROMPT,
            user=(
                f"Conversation-aware retrieved context:\n{context.prompt_context}\n\n"
                f"Question:\n{request.message}\n\n"
                "Answer with grounded analysis and a short citation list."
            ),
            model=model,
            history=history,
        )
    except RuntimeError as exc:
        metrics.record("model", "unavailable", model_started)
        metrics.finish("unavailable")
        return safe_ask_error(
            http_request,
            status_code=502,
            code="MODEL_UNAVAILABLE",
            detail="The AI service is temporarily unavailable.",
            internal_detail=f"{type(exc).__name__}: {exc}",
        )
    metrics.record("model", "success", model_started)

    reply = _ensure_citation_text(reply, context)
    persistence_started = metrics.start()
    assistant_persisted = save_chat_message(
        user.id,
        "assistant",
        reply,
        request.event_id,
    )
    metrics.record(
        "assistant_persistence",
        "suppressed_failure" if assistant_persisted is False else "success",
        persistence_started,
    )
    _record_audit(
        user_id=user.id,
        event_id=request.event_id,
        question=request.message,
        model=model,
        retrieval_provider=retrieval_provider.provider_name,
        context=context,
        retrieval=retrieval,
        started=started,
    )
    metrics.finish("success")
    return ChatResponse(
        reply=reply,
        event_id=request.event_id,
        model=model,
        intent=retrieval.intent.name,
        citations=[citation_to_dict(citation) for citation in context.citations],
        related_questions=context.related_questions,
    )


@router.get("/history")
async def chat_history(
    user: UserDep,
    event_id: int | None = None,
) -> list[dict[str, str | int | None]]:
    return get_chat_history(user.id, event_id)


def _record_audit(
    *,
    user_id: str,
    event_id: int | None,
    question: str,
    model: str,
    retrieval_provider: str,
    context: BuiltContext,
    retrieval: Any,
    started: float,
) -> None:
    record_chat_retrieval_audit(
        user_id=user_id,
        event_id=event_id,
        question=question,
        detected_intent=retrieval.intent.name,
        retrieval_provider=retrieval_provider,
        retrieved_chunks=retrieval.hits,
        graph_entities=context.graph_facts,
        citations=context.citations,
        related_questions=context.related_questions,
        model=model,
        response_latency_ms=_elapsed_ms(started),
        retrieval_latency_ms=retrieval.retrieval_latency_ms,
        context_tokens=context.estimated_tokens,
    )


def _ensure_citation_text(reply: str, context: BuiltContext) -> str:
    if "citation" in reply.lower() or not context.citations:
        return reply
    lines = [reply.rstrip(), "", "Citations:"]
    for index, citation in enumerate(context.citations[:5], start=1):
        lines.append(
            f"{index}. {citation.title} | {citation.issuer or 'Unknown issuer'} | "
            f"{citation.issue_date or 'Unknown date'} | {citation.source_url} | "
            f"chunk={citation.chunk_id or 'graph'}, page={citation.page_number or 'unknown'}"
        )
    return "\n".join(lines)


def _elapsed_ms(started: float) -> int:
    return max(0, int((time.perf_counter() - started) * 1000))


def _schedule_decision_shadow(
    *,
    background_tasks: BackgroundTasks,
    metrics: AskMetrics,
    query: str,
    legacy_intent: IntentName,
) -> None:
    if not settings.ask_ai_decision_engine_enabled:
        return
    try:
        service = get_decision_shadow_service(metrics.correlation_id)
        background_tasks.add_task(
            service.evaluate_and_record,
            query=query,
            legacy_intent=legacy_intent,
        )
    except Exception:
        return


def get_decision_shadow_service(correlation_id: str) -> DecisionShadowService:
    return DecisionShadowService(
        recorder=LoggingShadowComparisonRecorder(
            correlation_id=correlation_id,
        )
    )
