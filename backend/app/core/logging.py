"""Structured JSON logging with request/correlation context automatically
attached to every log line. Configure once at startup via configure_logging();
everywhere else just `logger = get_logger(__name__)`."""
import logging
import sys

import structlog

from app.context.request import get_correlation_id, get_request_id, get_user_id


def _bind_context(_, __, event_dict):
    request_id = get_request_id()
    correlation_id = get_correlation_id()
    user_id = get_user_id()
    if request_id:
        event_dict["request_id"] = request_id
    if correlation_id:
        event_dict["correlation_id"] = correlation_id
    if user_id:
        event_dict["user_id"] = user_id
    return event_dict


def configure_logging(*, level: str = "INFO", json_output: bool = True) -> None:
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)

    shared_processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        _bind_context,
    ]

    renderer = structlog.processors.JSONRenderer() if json_output else structlog.dev.ConsoleRenderer()

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None):
    return structlog.get_logger(name)
