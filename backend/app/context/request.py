"""Request-scoped context propagated via contextvars. Set once by
middleware/request_context.py at the start of a request; readable from
anywhere downstream (services, repositories, jobs after being re-bound
in the worker) without threading extra parameters through every call.
This is what lets one correlation_id tie together:
  HTTP request -> service call -> provider call -> webhook -> worker job
"""
from contextvars import ContextVar

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_correlation_id: ContextVar[str | None] = ContextVar("correlation_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_user_role: ContextVar[str | None] = ContextVar("user_role", default=None)


def set_request_id(value: str | None) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()


def set_correlation_id(value: str | None) -> None:
    _correlation_id.set(value)


def get_correlation_id() -> str | None:
    return _correlation_id.get()


def set_user_id(value: str | None) -> None:
    _user_id.set(value)


def get_user_id() -> str | None:
    return _user_id.get()


def set_user_role(value: str | None) -> None:
    _user_role.set(value)


def get_user_role() -> str | None:
    return _user_role.get()


def reset_context() -> None:
    _request_id.set(None)
    _correlation_id.set(None)
    _user_id.set(None)
    _user_role.set(None)
