from __future__ import annotations

import time
from typing import Literal

from fastapi import Request

from backend.api.ask_errors import correlation_id_for
from backend.core.logging import log_event

AskMetricStage = Literal[
    "auth",
    "user_persistence",
    "retrieval",
    "model",
    "assistant_persistence",
    "request",
]
AskMetricOutcome = Literal[
    "success",
    "no_match",
    "skipped",
    "suppressed_failure",
    "unavailable",
]


class AskMetrics:
    def __init__(self, request: Request) -> None:
        self.correlation_id = correlation_id_for(request)
        self.request_started = getattr(
            request.state,
            "ask_started_at",
            time.perf_counter(),
        )

    @staticmethod
    def start() -> float:
        return time.perf_counter()

    def record(
        self,
        stage: AskMetricStage,
        outcome: AskMetricOutcome,
        started: float,
    ) -> None:
        log_event(
            "ask_stage_metric",
            correlation_id=self.correlation_id,
            metric_stage=stage,
            outcome=outcome,
            duration_ms=max(0, int((time.perf_counter() - started) * 1000)),
        )

    def finish(self, outcome: AskMetricOutcome) -> None:
        self.record("request", outcome, self.request_started)
