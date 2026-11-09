"""App factory. Registers middleware, exception handling, and routers.
Routers are thin; everything they call is defined elsewhere per the
architecture plan — this file's job is wiring, nothing else.

The scheduler no longer runs in this process's lifespan — see
scheduler/run.py and its leader-election lock for why (N API replicas
must not each run their own reconciliation sweep).
"""
import time

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from starlette.responses import Response

from app.core.config import settings
from app.core.exceptions import VividGenError
from app.core.logging import configure_logging, get_logger
from app.middleware.request_context import RequestContextMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.monitoring.metrics import (
    http_request_duration_seconds,
    http_requests_total,
)
from app.monitoring.sentry import init_sentry
from app.routers import (
    account,
    admin,
    brand_kits,
    credits,
    exports,
    generations,
    health,
    media,
    models,
    productions,
    projects,
    uploads,
    webhooks,
    workflows,
)

configure_logging(
    level=settings.log_level,
    json_output=settings.log_json,
)

logger = get_logger(__name__)
init_sentry()

_is_prod = settings.app_env == "production"

app = FastAPI(
    title=settings.app_name,
    version="3.0.0",
    docs_url=None if _is_prod else "/docs",
    redoc_url=None if _is_prod else "/redoc",
    openapi_url=None if _is_prod else "/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins or [],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)


@app.middleware("http")
async def metrics_middleware(request: Request, call_next):
    start = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception:
        elapsed = time.perf_counter() - start

        logger.exception(
            "Unhandled HTTP request exception",
            extra={
                "method": request.method,
                "path": request.url.path,
                "duration_ms": round(elapsed * 1000, 2),
                "event": "http_request_exception",
                "request_id": getattr(
                    request.state,
                    "request_id",
                    None,
                ),
                "correlation_id": getattr(
                    request.state,
                    "correlation_id",
                    None,
                ),
            },
        )
        raise

    elapsed = time.perf_counter() - start

    http_requests_total.labels(
        request.method,
        request.url.path,
        response.status_code,
    ).inc()

    http_request_duration_seconds.labels(
        request.method,
        request.url.path,
    ).observe(elapsed)

    return response


@app.exception_handler(VividGenError)
async def domain_error_handler(
    request: Request,
    exc: VividGenError,
):
    """Convert typed domain exceptions into HTTP responses."""
    # Expected domain errors are logged at warning level rather than
    # error level, to distinguish normal business failures from bugs.
    logger.warning(
        "Domain exception",
        extra={
            "event": "domain_exception",
            "method": request.method,
            "path": request.url.path,
            "status_code": exc.http_status,
            "request_id": getattr(
                request.state,
                "request_id",
                None,
            ),
            "correlation_id": getattr(
                request.state,
                "correlation_id",
                None,
            ),
            "error_type": type(exc).__name__,
        },
    )

    return JSONResponse(
        status_code=exc.http_status,
        content={"error": exc.to_dict()},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(
    request: Request,
    exc: Exception,
):
    """Log unexpected API exceptions with a full traceback."""
    logger.error(
        "Unhandled API exception",
        exc_info=(type(exc), exc, exc.__traceback__),
        extra={
            "event": "unhandled_api_exception",
            "method": request.method,
            "path": request.url.path,
            "request_id": getattr(
                request.state,
                "request_id",
                None,
            ),
            "correlation_id": getattr(
                request.state,
                "correlation_id",
                None,
            ),
            "error_type": type(exc).__name__,
        },
    )

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
        },
    )


@app.get("/metrics")
async def metrics(
    x_metrics_token: str | None = Header(default=None),
):
    # Keep production metrics protected by the configured shared token.
    if _is_prod:
        if (
            not settings.metrics_token
            or x_metrics_token != settings.metrics_token
        ):
            raise HTTPException(404)

    return Response(
        generate_latest(),
        media_type=CONTENT_TYPE_LATEST,
    )


app.include_router(health.router)
app.include_router(generations.router, prefix=settings.api_prefix)
app.include_router(uploads.router, prefix=settings.api_prefix)
app.include_router(credits.router, prefix=settings.api_prefix)
app.include_router(account.router, prefix=settings.api_prefix)
app.include_router(models.router, prefix=settings.api_prefix)
app.include_router(webhooks.router, prefix=settings.api_prefix)
app.include_router(media.router, prefix=settings.api_prefix)
app.include_router(projects.router, prefix=settings.api_prefix)
app.include_router(admin.router, prefix=settings.api_prefix)
app.include_router(workflows.router, prefix=settings.api_prefix)
app.include_router(brand_kits.router, prefix=settings.api_prefix)
app.include_router(exports.router, prefix=settings.api_prefix)
app.include_router(productions.router, prefix=settings.api_prefix)
