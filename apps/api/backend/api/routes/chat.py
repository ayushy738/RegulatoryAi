import time
from typing import Any
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, status
from fastapi.responses import JSONResponse

from backend.api.ask_errors import safe_ask_error
from backend.api.ask_metrics import AskMetricOutcome, AskMetrics
from backend.api.deps import UserDep
from backend.api.ratelimit import limit_chat
from backend.ask.decision.shadow import (
    DecisionShadowService,
    LoggingShadowComparisonRecorder,
)
from backend.ask.general_ai import (
    GeneralAIExecutionRequest,
    GeneralAIExecutionResult,
    GeneralAIExecutionState,
    execute_general_ai,
)
from backend.ask.knowledge_modes import (
    KnowledgeModeRequest,
    OfficialEvidenceOutcome,
    select_knowledge_modes,
)
from backend.ask.persistence import AskPersistenceService
from backend.core.config import settings
from backend.core.llm import get_llm_client
from backend.core.logging import log_event
from backend.core.models import ChatRequest, ChatResponse
from backend.core.repository import chat_history as get_chat_history
from backend.core.repository import (
    citations_for_assistant_messages,
    citations_for_question,
    get_chat_conversation_messages,
    list_chat_conversations,
    save_chat_message,
)
from backend.rag.audit import record_chat_retrieval_audit
from backend.rag.context_builder import (
    build_context,
    grounded_user_prompt,
    max_prompt_context_chars,
)
from backend.rag.models import BuiltContext, IntentName, citation_to_dict
from backend.rag.retrieval import RetrievalProviderFactory

router = APIRouter(prefix="/chat", tags=["chat"])

NO_EVIDENCE_REPLY = (
    "I do not have enough retrieved evidence to answer this from the regulatory "
    "corpus. No citation-backed chunks or graph facts were found for this question."
)
GENERAL_AI_SCOPE = "India energy sector regulation"
GENERAL_AI_TIMEOUT_MS = 25_000

SYSTEM_PROMPT = (
    "You are a regulatory analyst assistant for India's energy sector. "
    "Answer using ONLY the retrieved evidence and knowledge graph facts. "
    "Every factual claim must be grounded in the citation inventory. Include concise "
    "citations with document title, issuer, issue date, and source URL when available. "
    "Do not include internal chunk IDs or retrieval scores. If evidence is insufficient, "
    "say so clearly. Distinguish fact from inference. Do not invent obligations, "
    "deadlines, amendments, stakeholders, or relationships."
)


def _conversation_title(message: str) -> str:
    cleaned = " ".join(message.split())
    if not cleaned:
        return "New chat"
    if len(cleaned) <= 72:
        return cleaned
    return f"{cleaned[:69].rstrip()}..."


def _persisted_message_id(result: int | bool | None) -> int | None:
    """Extract a real chat_messages.id from a persistence result."""

    if isinstance(result, bool) or not isinstance(result, int):
        return None
    return result


def _resolve_session_id(user_id: str, request: ChatRequest) -> str:
    service = AskPersistenceService()
    if request.session_id:
        owned = service.get_session(
            session_id=UUID(request.session_id),
            user_id=UUID(user_id),
        )
        if owned is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found",
            )
        return str(owned.id)
    created = service.create_session(
        user_id=UUID(user_id),
        event_id=request.event_id,
        title=_conversation_title(request.message),
    )
    log_event(
        "ask_conversation_created",
        session_id=str(created.id),
        user_id=user_id,
    )
    return str(created.id)


@router.post("", response_model=ChatResponse, dependencies=[Depends(limit_chat)])
async def chat(
    request: ChatRequest,
    user: UserDep,
    http_request: Request,
    background_tasks: BackgroundTasks,
) -> ChatResponse | JSONResponse:
    started = time.perf_counter()
    metrics = AskMetrics(http_request)
    log_event(
        "ask_request_started",
        correlation_id=metrics.correlation_id,
        event_id=request.event_id,
        message_length=len(request.message),
        session_id=request.session_id,
    )
    metrics.record("auth", "success", metrics.request_started)
    model = settings.llm_model_chat or "offline-demo"
    session_id = _resolve_session_id(user.id, request)
    log_event(
        "ask_message_created",
        correlation_id=metrics.correlation_id,
        session_id=session_id,
        role="user",
    )

    prior = get_chat_conversation_messages(user.id, session_id) or []
    history = [
        {"role": str(item["role"]), "content": str(item["content"])}
        for item in prior[-8:]
        if item.get("role") in {"user", "assistant"} and item.get("content")
    ]
    if not history:
        history = [
            {"role": item["role"], "content": item["content"]}
            for item in reversed(get_chat_history(user.id, request.event_id)[-8:])
        ]

    persistence_started = metrics.start()
    user_persisted = save_chat_message(
        user.id,
        "user",
        request.message,
        request.event_id,
        session_id=session_id,
    )
    metrics.record(
        "user_persistence",
        "suppressed_failure" if user_persisted is False else "success",
        persistence_started,
    )

    retrieval_provider = RetrievalProviderFactory.get_provider()
    retrieval_started = metrics.start()
    try:
        log_event(
            "ask_retrieval_started",
            correlation_id=metrics.correlation_id,
            event_id=request.event_id,
            session_id=session_id,
            retrieval_provider=retrieval_provider.provider_name,
        )
        retrieval = retrieval_provider.hybrid_search(
            request.message,
            limit=settings.rag_top_k,
            event_id=request.event_id,
        )
    except Exception as exc:
        metrics.record("retrieval", "unavailable", retrieval_started)
        outage_reply = _general_ai_reply_or_none(
            await _general_ai_knowledge(
                request.message,
                official_outcome=OfficialEvidenceOutcome.UNAVAILABLE,
                correlation_id=metrics.correlation_id,
                event_id=request.event_id,
            )
        )
        if outage_reply is None:
            metrics.finish("unavailable")
            return safe_ask_error(
                http_request,
                status_code=500,
                code="RETRIEVAL_UNAVAILABLE",
                detail="Regulatory evidence retrieval is temporarily unavailable.",
                internal_detail=f"{type(exc).__name__}: {exc}",
            )
        persistence_started = metrics.start()
        assistant_persisted = save_chat_message(
            user.id,
            "assistant",
            outage_reply,
            request.event_id,
            session_id=session_id,
            knowledge_basis="general",
        )
        metrics.record(
            "assistant_persistence",
            "suppressed_failure" if assistant_persisted is False else "success",
            persistence_started,
        )
        metrics.finish("success")
        return ChatResponse(
            reply=outage_reply,
            event_id=request.event_id,
            session_id=session_id,
            model=model,
            intent="general",
            knowledge_basis="general",
            citations=[],
            related_questions=[],
        )
    metrics.record(
        "retrieval",
        "success" if retrieval.hits else "no_match",
        retrieval_started,
    )
    log_event(
        "ask_retrieval_finished",
        correlation_id=metrics.correlation_id,
        event_id=request.event_id,
        session_id=session_id,
        hits=len(retrieval.hits),
        citations=len(retrieval.citations),
        graph_facts=len(retrieval.graph_facts),
        intent=retrieval.intent.name,
    )
    _schedule_decision_shadow(
        background_tasks=background_tasks,
        metrics=metrics,
        query=request.message,
        legacy_intent=retrieval.intent.name,
    )
    log_event(
        "ask_context_build_started",
        correlation_id=metrics.correlation_id,
        event_id=request.event_id,
    )
    # Parallel enforces a 20k-character per-message limit. Token budgeting alone
    # still fits ~14 full evidence blocks (~30k chars). Bound prompt_context so
    # the grounded user message stays under that provider cap.
    context = build_context(
        retrieval,
        max_prompt_chars=max_prompt_context_chars(request.message),
    )
    log_event(
        "ask_context_build_finished",
        correlation_id=metrics.correlation_id,
        event_id=request.event_id,
        citations=len(context.citations),
        graph_facts=len(context.graph_facts),
        estimated_tokens=context.estimated_tokens,
        prompt_chars=len(context.prompt_context),
    )
    if not context.citations:
        general_started = metrics.start()
        general_result = await _general_ai_knowledge(
            request.message,
            correlation_id=metrics.correlation_id,
            event_id=request.event_id,
        )
        general_reply = _general_ai_reply_or_none(general_result)
        if general_reply is None:
            metrics.record("model", "skipped", general_started)
            reply = NO_EVIDENCE_REPLY
            request_outcome: AskMetricOutcome = "no_match"
            model_used = model
            knowledge_basis = "none"
        else:
            metrics.record("model", "success", general_started)
            reply = general_reply
            request_outcome = "success"
            model_used = (
                general_result.provider_identity.model
                if general_result is not None
                and general_result.provider_identity is not None
                else model
            )
            knowledge_basis = "general"
        persistence_started = metrics.start()
        assistant_persisted = save_chat_message(
            user.id,
            "assistant",
            reply,
            request.event_id,
            session_id=session_id,
            knowledge_basis=knowledge_basis,
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
            assistant_message_id=_persisted_message_id(assistant_persisted),
            model=model_used,
            retrieval_provider=retrieval_provider.provider_name,
            context=context,
            retrieval=retrieval,
            started=started,
        )
        metrics.finish(request_outcome)
        return ChatResponse(
            reply=reply,
            event_id=request.event_id,
            session_id=session_id,
            model=model_used,
            intent=retrieval.intent.name,
            knowledge_basis=knowledge_basis,
            citations=[],
            related_questions=context.related_questions,
        )

    model_started = metrics.start()
    try:
        log_event(
            "llm_execution_started",
            correlation_id=metrics.correlation_id,
            event_id=request.event_id,
            session_id=session_id,
            model=model,
            citations=len(context.citations),
        )
        reply = get_llm_client().complete_text(
            system=SYSTEM_PROMPT,
            user=grounded_user_prompt(
                prompt_context=context.prompt_context,
                question=request.message,
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
    log_event(
        "llm_execution_finished",
        correlation_id=metrics.correlation_id,
        event_id=request.event_id,
        session_id=session_id,
        model=model,
        reply_length=len(reply),
        citations=len(context.citations),
    )

    reply = _ensure_citation_text(reply, context)
    persistence_started = metrics.start()
    assistant_persisted = save_chat_message(
        user.id,
        "assistant",
        reply,
        request.event_id,
        session_id=session_id,
        knowledge_basis="official",
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
        assistant_message_id=_persisted_message_id(assistant_persisted),
        model=model,
        retrieval_provider=retrieval_provider.provider_name,
        context=context,
        retrieval=retrieval,
        started=started,
    )
    metrics.finish("success")
    log_event(
        "ask_grounded_answer_finished",
        correlation_id=metrics.correlation_id,
        event_id=request.event_id,
        session_id=session_id,
        model=model,
        intent=retrieval.intent.name,
        citations=len(context.citations),
        persisted=assistant_persisted is not False,
        knowledge_basis="official",
    )
    return ChatResponse(
        reply=reply,
        event_id=request.event_id,
        session_id=session_id,
        model=model,
        intent=retrieval.intent.name,
        knowledge_basis="official",
        citations=[citation_to_dict(citation) for citation in context.citations],
        related_questions=context.related_questions,
    )


@router.get("/conversations")
async def list_conversations(user: UserDep) -> list[dict[str, Any]]:
    log_event("ask_conversations_listed", user_id=user.id)
    return list_chat_conversations(user.id)


@router.get("/conversations/{session_id}")
async def get_conversation(session_id: str, user: UserDep) -> dict[str, Any]:
    rows = get_chat_conversation_messages(user.id, session_id)
    if rows is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found",
        )
    messages: list[dict[str, Any]] = []
    assistant_ids: list[int] = []
    for row in rows:
        role = str(row["role"])
        item: dict[str, Any] = {
            "id": row["id"],
            "role": role,
            "content": str(row["content"]),
            "created_at": row["created_at"],
            "knowledge_basis": row.get("knowledge_basis"),
            "citations": [],
        }
        if role == "assistant" and isinstance(row["id"], int):
            assistant_ids.append(int(row["id"]))
        messages.append(item)

    citations_by_message = citations_for_assistant_messages(user.id, assistant_ids)
    # Messages written before message-bound audits carry no knowledge_basis. Only
    # those may fall back to question-text matching, and that fallback can never
    # reach an audit row already bound to another answer.
    pending_question: str | None = None
    for item in messages:
        if item["role"] == "user":
            pending_question = item["content"]
            continue
        if item["role"] != "assistant":
            continue
        bound = citations_by_message.get(item["id"])
        if bound is not None:
            item["citations"] = bound
        elif item["knowledge_basis"] is None and pending_question:
            item["citations"] = citations_for_question(user.id, pending_question)
        pending_question = None

    log_event(
        "ask_conversation_loaded",
        session_id=session_id,
        message_count=len(messages),
        message_bound_citations=len(citations_by_message),
    )
    return {"id": session_id, "messages": messages}


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
    assistant_message_id: int | None = None,
) -> None:
    record_chat_retrieval_audit(
        user_id=user_id,
        event_id=event_id,
        question=question,
        assistant_message_id=assistant_message_id,
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


async def _general_ai_knowledge(
    question: str,
    *,
    official_outcome: OfficialEvidenceOutcome = (
        OfficialEvidenceOutcome.HEALTHY_NO_MATCH
    ),
    correlation_id: str,
    event_id: int | None,
) -> GeneralAIExecutionResult | None:
    if not settings.ask_ai_general_mode_enabled:
        return None
    log_event(
        "ask_general_ai_started",
        correlation_id=correlation_id,
        event_id=event_id,
        official_outcome=official_outcome.value,
    )
    try:
        result = await execute_general_ai(
            GeneralAIExecutionRequest(
                query=question,
                resolved_scope=(GENERAL_AI_SCOPE,),
                mode_decision=select_knowledge_modes(
                    KnowledgeModeRequest(
                        official_outcome=official_outcome,
                        qualified_general_fallback_allowed=(
                            official_outcome
                            is OfficialEvidenceOutcome.UNAVAILABLE
                        ),
                    )
                ),
                timeout_ms=GENERAL_AI_TIMEOUT_MS,
            )
        )
    except Exception as exc:
        log_event(
            "ask_general_ai_finished",
            correlation_id=correlation_id,
            event_id=event_id,
            state="unavailable",
            safe_code="GENERAL_AI_CAPABILITY_UNAVAILABLE",
            internal_detail=f"{type(exc).__name__}: {exc}",
        )
        return None
    log_event(
        "ask_general_ai_finished",
        correlation_id=correlation_id,
        event_id=event_id,
        state=result.state.value,
        health=result.health.value,
        safe_code=result.safe_code,
        provider=(
            result.provider_identity.provider
            if result.provider_identity is not None
            else None
        ),
        units=len(result.units),
    )
    return result


def _general_ai_reply_or_none(
    result: GeneralAIExecutionResult | None,
) -> str | None:
    if result is None or result.state is not GeneralAIExecutionState.SATISFIED:
        return None
    return _general_ai_reply(result)


def _general_ai_reply(result: GeneralAIExecutionResult) -> str | None:
    blocks: list[str] = []
    for unit in result.units:
        payload = unit.payload
        blocks.append(payload.content.strip())
        if payload.assumptions:
            blocks.append(
                "Assumptions:\n"
                + "\n".join(f"- {item}" for item in payload.assumptions)
            )
        if payload.uncertainty_statements:
            blocks.append(
                "Uncertainty:\n"
                + "\n".join(
                    f"- {item}" for item in payload.uncertainty_statements
                )
            )
        if payload.required_disclosure is not None:
            blocks.append(payload.required_disclosure)
    reply = "\n\n".join(block for block in blocks if block)
    return reply or None


def _ensure_citation_text(reply: str, context: BuiltContext) -> str:
    if "citation" in reply.lower() or not context.citations:
        return reply
    lines = [reply.rstrip(), "", "Sources"]
    for index, citation in enumerate(context.citations[:8], start=1):
        issuer = citation.issuer or "Official source"
        date_label = (
            citation.issue_date.isoformat()
            if citation.issue_date is not None
            else None
        )
        meta = issuer if date_label is None else f"{issuer} · {date_label}"
        lines.append(f"{index}. {citation.title} — {meta}")
        if citation.source_url:
            lines.append(f"   {citation.source_url}")
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
