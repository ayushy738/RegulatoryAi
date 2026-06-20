import logging
import sys
from typing import Any

import sentry_sdk
import structlog

from backend.core.config import settings


def configure_logging() -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=logging.INFO)
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )
    if settings.sentry_dsn:
        sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)


def log_event(stage: str, source_code: str | None = None, **fields: Any) -> None:
    logger = structlog.get_logger("regulatory_ai")
    logger.info("pipeline_event", stage=stage, source_code=source_code, **fields)
