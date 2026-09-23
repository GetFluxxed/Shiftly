"""Shared HTTP mechanics independent of feature routers."""
from functools import partial
from urllib.parse import urlparse

import anyio
from fastapi.responses import JSONResponse
from backend.shiftly.identity.contracts import IdentityError, require_store_context

ACCOUNT_COOKIES = ("shiftly_account_session", "shiftly_manager_session", "shiftly_crew_session")
ERROR_STATUS = {
    "invalid": 400, "unauthenticated": 401, "forbidden": 403,
    "not_found": 404, "conflict": 409, "limited": 429, "unavailable": 503,
}


async def call(function, *args, **kwargs):
    return await anyio.to_thread.run_sync(partial(function, *args, **kwargs))


def error_response(error):
    return JSONResponse(status_code=ERROR_STATUS.get(error.code, 503), content={"error": str(error)})


def same_origin(request):
    origin = request.headers.get("origin")
    if origin:
        parsed = urlparse(origin)
        if parsed.scheme not in {"http", "https"} or parsed.netloc != request.headers.get("host"):
            raise IdentityError("forbidden", "Cross-origin account changes are not permitted.")
    if request.headers.get("sec-fetch-site") == "cross-site":
        raise IdentityError("forbidden", "Cross-origin account changes are not permitted.")


def store_precondition(fields, resolved):
    """An optional stale-tab precondition, never a source of store authority."""
    if "expectedStoreId" not in fields:
        return
    require_store_context(resolved, fields["expectedStoreId"])
