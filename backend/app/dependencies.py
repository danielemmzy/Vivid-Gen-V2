"""Shared FastAPI dependencies. Thin on purpose — routers depend on these,
never on repositories or the DB session directly.

Ordering matters here and is easy to get subtly wrong: `db_session` must
not be resolvable before `current_user_id` has run, because `get_db()`
reads the user_id contextvar to set the RLS session variable for the
transaction. FastAPI resolves a dependency's own sub-dependencies before
calling it, and caches each dependency callable's result per request — so
making `db_session` declare `current_user_id` as its own dependency
guarantees the ordering AND means routers that already separately depend
on `current_user_id` get the cached result, not a second HMAC check."""
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.context.request import set_user_id, set_user_role
from app.core.config import settings
from app.core.database import get_db, get_db_as_system
from app.core.exceptions import ForbiddenError
from app.core.security import InternalPrincipal, require_internal_user
from app.middleware.rate_limit import enforce_rate_limit


async def current_principal(
    request: Request,
    principal: InternalPrincipal = Depends(require_internal_user),
) -> InternalPrincipal:
    set_user_id(principal.user_id)
    set_user_role(principal.role)
    await enforce_rate_limit(request, principal.user_id, endpoint=request.url.path)
    return principal


async def current_user_id(principal: InternalPrincipal = Depends(current_principal)) -> str:
    return principal.user_id


def require_role(*allowed_roles: str):
    """Dependency factory for admin/support/etc-only endpoints:
    `Depends(require_role("admin", "support"))`. Role comes from the
    HMAC-signed claim Next.js sends — see core/security.py — never from
    anything the request body or an unsigned header could influence."""

    async def _check(principal: InternalPrincipal = Depends(current_principal)) -> InternalPrincipal:
        if principal.role not in allowed_roles:
            raise ForbiddenError(
                f"This action requires one of: {', '.join(allowed_roles)}",
                details={"required_roles": list(allowed_roles), "actual_role": principal.role},
            )
        return principal

    return _check


async def require_generations_enabled() -> None:
    """The global kill switch — see architecture review's rate-limiting
    gap. Flip GENERATIONS_ENABLED=false to immediately stop all new
    generation submission (e.g. during a fal.ai incident or a runaway-cost
    event) without taking the whole API down; reads, renames, and the
    credits/models endpoints keep working."""
    if not settings.generations_enabled:
        raise HTTPException(503, "Generation is temporarily disabled — please try again shortly")


async def db_session(_principal: InternalPrincipal = Depends(current_principal)) -> AsyncSession:
    """The session every authenticated router should use. Guarantees the
    RLS session variable (app.current_user_id) is set before any query
    runs on this session — see core/database.py."""
    async for session in get_db():
        yield session


async def system_db_session() -> AsyncSession:
    """For the small set of routes with no per-user auth context by
    design — webhooks (authenticated by provider signature, not a user
    session) and internal/admin tooling. RLS policies grant these full
    access via app.is_system_context; never wire this into a router that
    also exposes user-supplied filters, since RLS is the only thing
    stopping a cross-user read on this session."""
    async for session in get_db_as_system():
        yield session
