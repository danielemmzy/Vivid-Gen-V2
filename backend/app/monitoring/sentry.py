"""Sentry wiring. Previously SENTRY_DSN existed in settings but nothing
ever called sentry_sdk.init() — this is what the architecture review meant
by "not actually finished." Call `init_sentry()` once at process startup
(main.py for the API, workers/worker.py for ARQ) and `attach_context()` at
the point an error is about to be reported so it carries the same
request_id/correlation_id/user_id that the structured logs already have —
that's what makes a Sentry issue and a log line for the same failure
findable as the same event.
"""
import sentry_sdk
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.starlette import StarletteIntegration

from app.context.request import get_correlation_id, get_request_id, get_user_id
from app.core.config import settings


def init_sentry() -> None:
    if not settings.sentry_dsn:
        return
    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        release=None,  # wire to your deploy's git SHA / version tag in CI
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )


def attach_context(**extra: str | int | None) -> None:
    """Call right before re-raising/logging an error you want in Sentry
    with full trace context — e.g. inside GenerationService's failure
    paths, passing generation_id/provider_request_id as `extra`."""
    if not settings.sentry_dsn:
        return
    with sentry_sdk.configure_scope() as scope:
        scope.set_tag("request_id", get_request_id())
        scope.set_tag("correlation_id", get_correlation_id())
        scope.set_tag("user_id", get_user_id())
        for key, value in extra.items():
            scope.set_extra(key, value)
