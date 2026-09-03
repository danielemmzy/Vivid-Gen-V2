"""Baseline security response headers — none of these existed before.
This is not a substitute for the CORS/auth/RLS controls elsewhere; it's
defense-in-depth against browser-side attacks (clickjacking, MIME
sniffing, referrer leakage) on the small surface of this API that a
browser ever talks to directly (presigned upload PUTs, any HTML error
pages a proxy might inject)."""
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if settings.app_env == "production":
            response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
