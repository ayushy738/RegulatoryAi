from fastapi import APIRouter, Depends, HTTPException

from backend.api.deps import UserDep
from backend.api.ratelimit import limit_chat
from backend.core.config import settings
from backend.core.llm import get_llm_client
from backend.core.models import ChatRequest, ChatResponse
from backend.core.repository import chat_history as get_chat_history
from backend.core.repository import get_event, list_events, save_chat_message

router = APIRouter(prefix="/chat", tags=["chat"])

SYSTEM_PROMPT = (
    "You are a regulatory analyst assistant for India's energy sector. "
    "Answer using ONLY the provided context. Explain implications, who is affected, "
    "and what changed, in plain language. If the answer is not in the context, say so clearly. "
    "Distinguish fact from inference."
)


@router.post("", response_model=ChatResponse, dependencies=[Depends(limit_chat)])
async def chat(request: ChatRequest, user: UserDep) -> ChatResponse:
    context_events = list_events(user_id=user.id, page_size=5)
    if request.event_id is not None:
        selected = get_event(request.event_id, user.id)
        context_events = [selected] if selected else []
    context = "\n\n".join(
        f"Title: {event.title}\n"
        f"Body: {event.issuing_body}\n"
        f"Topics: {', '.join(event.topic_tags)}\n"
        f"Summary: {event.summary.plain_english_summary if event.summary else event.raw_summary}"
        for event in context_events
    )
    model = settings.llm_model_chat or "offline-demo"
    history = [
        {"role": item["role"], "content": item["content"]}
        for item in reversed(get_chat_history(user.id, request.event_id)[-8:])
    ]
    save_chat_message(user.id, "user", request.message, request.event_id)
    try:
        reply = get_llm_client().complete_text(
            system=SYSTEM_PROMPT,
            user=f"Context:\n{context}\n\nQuestion:\n{request.message}",
            model=model,
            history=history,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    save_chat_message(user.id, "assistant", reply, request.event_id)
    return ChatResponse(reply=reply, event_id=request.event_id, model=model)


@router.get("/history")
async def chat_history(
    user: UserDep,
    event_id: int | None = None,
) -> list[dict[str, str | int | None]]:
    return get_chat_history(user.id, event_id)
