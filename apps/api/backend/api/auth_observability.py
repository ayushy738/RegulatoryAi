from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from backend.core.db import session_scope
from backend.identity.repositories import AuthenticationMetricsRepository

logger = logging.getLogger(__name__)


def record_authentication_observation(
    *,
    source: Literal["supabase", "identity", "unknown"],
    outcome: Literal["success", "failure", "denied"],
    reason_code: str | None = None,
    observed_at: datetime | None = None,
) -> None:
    try:
        with session_scope() as session:
            AuthenticationMetricsRepository(session).increment(
                source=source,
                outcome=outcome,
                reason_code=reason_code,
                observed_at=observed_at,
            )
    except (SQLAlchemyError, RuntimeError):
        logger.warning(
            "authentication_metrics_write_failed",
            extra={"auth_source": source, "auth_outcome": outcome},
        )
