"""FastAPI adapter for the framework-free Accounts & Access contract."""
from functools import partial
from urllib.parse import urlparse

import anyio
import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.shiftly.core.dependencies import (
    AppContext, client_key, cookie_token, get_app_context, identity_credentials,
    named_account_token,
)
from backend.shiftly.core.request import RequestBodyError, bounded_json
from backend.shiftly.identity import IdentityError

router = APIRouter(prefix="/api/accounts")
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


def clear_cookies(response, context):
    for name in ACCOUNT_COOKIES:
        response.delete_cookie(name, path="/", secure=context.settings.secure_cookies,
                               httponly=True, samesite="strict")
    return response


def session_response(result, context):
    response = JSONResponse(status_code=200, content=result.response)
    response.set_cookie("shiftly_account_session", result.token, max_age=result.ttl, path="/",
                        httponly=True, samesite="strict", secure=context.settings.secure_cookies)
    for name in ACCOUNT_COOKIES[1:]:
        response.delete_cookie(name, path="/", secure=context.settings.secure_cookies,
                               httponly=True, samesite="strict")
    return response


async def principal(context, request):
    return await call(context.services.identity.resolve_principal, **identity_credentials(request))


async def require_named(context, request):
    resolved = await principal(context, request)
    if not resolved or not resolved.named:
        raise IdentityError("unauthenticated", "Named sign-in required.")
    return resolved


def store_precondition(fields, resolved):
    """An optional stale-tab precondition, never a source of store authority."""
    if "expectedStoreId" not in fields:
        return
    expected = fields["expectedStoreId"]
    if isinstance(expected, bool) or not isinstance(expected, int) or expected <= 0:
        raise IdentityError("invalid", "Expected store ID must be a positive integer.")
    if expected != resolved.store_id:
        raise IdentityError("conflict", "The selected store changed. Refresh and try again.")


@router.api_route("/{operation:path}", methods=["GET", "POST"])
async def account_route(operation: str, request: Request, context: AppContext = Depends(get_app_context)):
    """Translate HTTP fields explicitly; authorization belongs to account services."""
    accounts = context.services.accounts
    token = named_account_token(request)
    try:
        if request.method == "POST":
            same_origin(request)
        if operation == "status" and request.method == "GET":
            resolved = await principal(context, request)
            if not resolved or not resolved.named:
                return {"authenticated": False, "reauthenticationRequired": bool(resolved)}
            return {"authenticated": True, "actor": resolved.actor.as_dict(),
                    "stores": await call(accounts.authorized_stores, token)}
        if operation == "team" and request.method == "GET":
            await require_named(context, request)
            return await call(accounts.roster, token)
        if request.method != "POST":
            return JSONResponse(status_code=404, content={"error": "Not found."})
        if operation == "logout":
            # Logout deliberately clears ambiguous/expired credentials too.
            await call(accounts.logout, token)
            await call(context.services.identity.logout,
                       cookie_token(request, "shiftly_manager_session"), cookie_token(request, "shiftly_crew_session"))
            return clear_cookies(JSONResponse(content={"authenticated": False}), context)
        fields = await bounded_json(request, max_body=20_000, invalid_message="Invalid account request.")
        if operation == "login":
            return session_response(await call(accounts.login_payload, fields, client_key=client_key(request)), context)
        if operation == "activate":
            return session_response(await call(accounts.activate_invitation, fields.get("token"), fields.get("password"),
                                                client_key=client_key(request)), context)
        if operation == "reset-password":
            result = await call(accounts.reset_password, fields.get("token"), fields.get("password"), client_key=client_key(request))
            return clear_cookies(JSONResponse(content=result), context)
        resolved = await require_named(context, request)
        store_precondition(fields, resolved)
        reason = fields.get("reason", "")
        clear = False
        if operation == "logout-all":
            result = await call(accounts.logout_all, token)
            clear = True
        elif operation == "switch-store":
            return session_response(await call(accounts.switch_store, token, fields.get("storeId")), context)
        elif operation == "invitations":
            result = await call(accounts.invite, token, username=fields.get("username"), display_name=fields.get("displayName", ""),
                                role=fields.get("role", "crew"), capabilities=fields.get("capabilities", []),
                                store_id=fields.get("storeId"), expires_in=fields.get("expiresIn", 86400), reason=reason)
        elif operation == "invitations/reissue":
            result = await call(accounts.reissue_invitation, token, user_id=fields.get("userId"),
                                store_id=fields.get("storeId"), expires_in=fields.get("expiresIn", 86400), reason=reason)
        elif operation == "memberships":
            result = await call(accounts.set_membership, token, user_id=fields.get("userId"), role=fields.get("role"),
                                capabilities=fields.get("capabilities", []), active=fields.get("active", True),
                                store_id=fields.get("storeId"), reason=reason)
        elif operation == "business-memberships":
            result = await call(accounts.set_business_membership, token, user_id=fields.get("userId"), role=fields.get("role"),
                                capabilities=fields.get("capabilities", []), active=fields.get("active", True), reason=reason)
        elif operation == "transfer-ownership":
            result = await call(accounts.transfer_ownership, token, user_id=fields.get("userId"), reason=reason)
            clear = True
        elif operation == "suspend":
            result = await call(accounts.suspend_user, token, user_id=fields.get("userId"),
                                suspended=fields.get("suspended", True), reason=reason)
        elif operation == "password":
            result = await call(accounts.change_password, token, current_password=fields.get("currentPassword"),
                                new_password=fields.get("newPassword"))
            clear = True
        elif operation == "cutover":
            result = await call(accounts.cutover_store, token, store_id=fields.get("storeId"), reason=reason)
        else:
            return JSONResponse(status_code=404, content={"error": "Not found."})
        response = JSONResponse(content=result)
        return clear_cookies(response, context) if clear else response
    except IdentityError as error:
        return error_response(error)
    except (RequestBodyError, ValueError, TypeError, UnicodeError):
        return JSONResponse(status_code=400, content={"error": "Invalid account request."})
    except (psycopg.Error, RuntimeError):
        return JSONResponse(status_code=503, content={"error": "Account service is temporarily unavailable."})
