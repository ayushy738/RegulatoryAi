from __future__ import annotations

import time
from typing import Literal
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from backend.core.logging import log_event

AskErrorCode = Literal[
    "AUTH_REQUIRED",
    "RATE_LIMITED",
    "INVALID_QUESTION",
    "AMBIGUOUS_SCOPE",
    "RETRIEVAL_DEGRADED",
    "RETRIEVAL_UNAVAILABLE",
    "NO_GROUNDED_EVIDENCE",
    "MODEL_REJECTED_REQUEST",
    "MODEL_UNAVAILABLE",
    "CITATION_VERIFICATION_FAILED",
    "PERSISTENCE_FAILED",
    "RUN_CANCELLED",
]

CORRELATION_HEADER = "X-Correlation-ID"


class AskCorrelationMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        if scope["type"] != "http" or not (path == "/chat" or path.startswith("/chat/")):
            await self.app(scope, receive, send)
            return

        correlation_id = str(uuid4())
        scope.setdefault("state", {})["correlation_id"] = correlation_id
        scope["state"]["ask_started_at"] = time.perf_counter()

        async def send_with_correlation(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append(
                    (CORRELATION_HEADER.lower().encode("ascii"), correlation_id.encode("ascii"))
                )
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_correlation)


def correlation_id_for(request: Request) -> str:
    correlation_id = getattr(request.state, "correlation_id", None)
    return correlation_id if isinstance(correlation_id, str) else str(uuid4())


def safe_ask_error(
    request: Request,
    *,
    status_code: int,
    code: AskErrorCode,
    detail: str,
    internal_detail: str,
) -> JSONResponse:
    correlation_id = correlation_id_for(request)
    log_event(
        "ask_error",
        correlation_id=correlation_id,
        error_code=code,
        error_detail=internal_detail,
    )
    return JSONResponse(
        status_code=status_code,
        content={
            "detail": detail,
            "code": code,
            "correlation_id": correlation_id,
        },
    )
