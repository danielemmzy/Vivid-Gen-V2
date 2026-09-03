"""Binds request_id / correlation_id / user_id into contextvars for the
duration of one request, so every log line and metric emitted anywhere
down the call stack — router, service, provider client — carries them
without being passed explicitly. correlation_id is preserved across
service hops if the caller (Next.js) sends one; otherwise we mint one, so
a trace that starts in Next.js can be followed straight through fal.ai's
webhook and into the worker job."""
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.context.request import reset_context, set_correlation_id, set_request_id
from app.core.constants import CORRELATION_ID_HEADER, REQUEST_ID_HEADER
from app.core.logging import get_logger

logger = get_logger(__name__)


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        correlation_id = request.headers.get(CORRELATION_ID_HEADER) or request_id
        set_request_id(request_id)
        set_correlation_id(correlation_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "http_request", method=request.method, path=request.url.path, duration_ms=round(elapsed_ms, 2),
            )
            reset_context()

        response.headers[REQUEST_ID_HEADER] = request_id
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        return response
