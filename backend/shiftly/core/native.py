"""Shared bearer/session boundary for native feature routers.

Protected writes also recheck policy inside their service transaction using
accounts.require_selected_store; preliminary HTTP authorization is insufficient.
"""
import re
from fastapi.responses import JSONResponse
from backend.shiftly.identity.contracts import IdentityError
from .http import ACCOUNT_COOKIES, ERROR_STATUS, call, store_precondition


_BEARER = re.compile(r"Bearer ([A-Za-z0-9._~+/-]+={0,2})", re.IGNORECASE)


def native_token(request):
    """Never choose between multiple credentials, including empty auth cookies."""
    for item in ";".join(request.headers.getlist("cookie")).split(";"):
        if item.strip().partition("=")[0].strip() in ACCOUNT_COOKIES:
            raise IdentityError("unauthenticated", "Native sign-in cannot use browser sessions.")
    values = request.headers.getlist("authorization")
    if not values:
        return None
    if len(values) != 1 or len(values[0]) > 520:
        raise IdentityError("unauthenticated", "A single valid bearer session is required.")
    match = _BEARER.fullmatch(values[0])
    if not match:
        raise IdentityError("unauthenticated", "A single valid bearer session is required.")
    return match.group(1)


def native_session(result):
    return {**result.response, "sessionToken": result.token, "expiresIn": result.ttl}


def selected_store(fields, actor):
    if "expectedStoreId" not in fields:
        raise IdentityError("invalid", "Expected store ID is required.")
    store_precondition(fields, actor)


async def require_actor(context, token, *, capability=None):
    return await call(context.services.accounts.resolve_actor, token, capability=capability)


def unavailable():
    return JSONResponse(status_code=503, content={"error": "Service is temporarily unavailable."})


def error_response(error):
    # Browser adapters retain their existing {error} response shape.
    reason = error.reason or {
        "unauthenticated": "session_invalid", "invalid": "validation_failed",
    }.get(error.code, error.code)
    return JSONResponse(status_code=ERROR_STATUS.get(error.code, 503),
                        content={"error": str(error), "errorCode": reason})
