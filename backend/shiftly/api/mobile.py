"""Native-only transport for the existing named-account and reporting services.

Browser adapters remain cookie-only. Native sessions have the same opaque,
hashed, expiring and revocable server-side records; only their delivery differs.
"""
import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.shiftly.core.dependencies import AppContext, client_key, get_app_context
from backend.shiftly.core.request import RequestBodyError, bounded_json
from backend.shiftly.identity import IdentityError
from backend.shiftly.reports.errors import ReportRejected
from backend.shiftly.core.http import call, same_origin
from backend.shiftly.core.native import (
    native_token, native_session, selected_store, require_actor, unavailable, error_response,
)

router = APIRouter(prefix="/api/mobile")
@router.api_route("/accounts/{operation:path}", methods=["GET", "POST"])
async def accounts_route(operation: str, request: Request, context: AppContext = Depends(get_app_context)):
    accounts = context.services.accounts
    try:
        token = native_token(request)
        if request.method == "POST":
            same_origin(request)
        if operation == "status" and request.method == "GET":
            if token is None:
                return {"authenticated": False, "reauthenticationRequired": False}
            actor = await require_actor(context, token)
            return {"authenticated": True, "actor": actor.as_dict(),
                    "stores": await call(accounts.authorized_stores, token)}
        if operation == "management" and request.method == "GET":
            return await call(accounts.management, token)
        if operation == "team" and request.method == "GET":
            await require_actor(context, token)
            return await call(accounts.roster, token)
        if request.method != "POST":
            return JSONResponse(status_code=404, content={"error": "Not found."})
        if operation == "logout":
            # Logout remains idempotent even after expiry or revocation.
            return await call(accounts.logout, token)
        fields = await bounded_json(request, max_body=20_000, invalid_message="Invalid account request.")
        if operation == "login":
            return native_session(await call(accounts.login_payload, fields, client_key=client_key(request)))
        if operation == "activate":
            return native_session(await call(accounts.activate_invitation, fields.get("token"), fields.get("password"),
                                             client_key=client_key(request)))
        if operation == "reset-password":
            return await call(accounts.reset_password, fields.get("token"), fields.get("password"),
                              client_key=client_key(request))
        actor = await require_actor(context, token)
        selected_store(fields, actor)
        reason = fields.get("reason", "")
        if operation == "logout-all":
            return await call(accounts.logout_all, token)
        if operation == "switch-store":
            return native_session(await call(accounts.switch_store, token, fields.get("storeId")))
        if operation in {"password", "change-password"}:
            return await call(accounts.change_password, token, current_password=fields.get("currentPassword"),
                              new_password=fields.get("newPassword"))
        if operation == "invitations":
            return await call(accounts.invite, token, username=fields.get("username"), display_name=fields.get("displayName", ""),
                              role=fields.get("role", "crew"), capabilities=fields.get("capabilities", []),
                              store_id=fields.get("storeId"), expires_in=fields.get("expiresIn", 86400), reason=reason)
        if operation == "invitations/reissue":
            return await call(accounts.reissue_invitation, token, user_id=fields.get("userId"),
                              store_id=fields.get("storeId"), expires_in=fields.get("expiresIn", 86400), reason=reason)
        if operation == "memberships":
            return await call(accounts.set_membership, token, user_id=fields.get("userId"), role=fields.get("role"),
                              capabilities=fields.get("capabilities", []), active=fields.get("active", True),
                              store_id=fields.get("storeId"), reason=reason)
        if operation == "business-memberships":
            return await call(accounts.set_business_membership, token, user_id=fields.get("userId"), role=fields.get("role"),
                              capabilities=fields.get("capabilities", []), active=fields.get("active", True), reason=reason)
        if operation == "transfer-ownership":
            return await call(accounts.transfer_ownership, token, user_id=fields.get("userId"), reason=reason)
        if operation == "suspend":
            return await call(accounts.suspend_user, token, user_id=fields.get("userId"),
                              suspended=fields.get("suspended", True), reason=reason)
        if operation == "cutover":
            return await call(accounts.cutover_store, token, store_id=fields.get("storeId"), reason=reason)
        return JSONResponse(status_code=404, content={"error": "Not found."})
    except IdentityError as error:
        return error_response(error)
    except (RequestBodyError, ValueError, TypeError, UnicodeError):
        return JSONResponse(status_code=400, content={"error": "Invalid account request."})
    except (psycopg.Error, RuntimeError):
        return unavailable()


@router.get("/reports")
async def reports(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        token = native_token(request)
        await require_actor(context, token, capability="reports.view")
        return {"reports": await call(context.services.reports.list_for_actor, token, context.services.accounts,
                                      include_store=True)}
    except IdentityError as error:
        return error_response(error)
    except (psycopg.Error, RuntimeError):
        return unavailable()


@router.post("/reports", status_code=202)
async def submit_report(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        token = native_token(request)
        actor = await require_actor(context, token, capability="reports.submit")
        same_origin(request)
        if context.services.admission.report_limited(client_key(request)):
            return JSONResponse(status_code=429, content={"error": "Too many submissions. Try again later."})
        fields = await bounded_json(request, max_body=100_000, invalid_message="Invalid report format.")
        selected_store(fields, actor)
        _, created_at = await call(context.services.submission.submit, actor.store_id, fields,
                                   actor_token=token, accounts=context.services.accounts)
        return {"date": created_at.isoformat(), "status": "pending"}
    except IdentityError as error:
        return error_response(error)
    except ReportRejected as error:
        return JSONResponse(status_code=422, content={"error": error.reason})
    except (RequestBodyError, ValueError) as error:
        return JSONResponse(status_code=400, content={"error": str(error)})
    except (TypeError, UnicodeError):
        return JSONResponse(status_code=400, content={"error": "Invalid report format."})
    except (psycopg.Error, RuntimeError):
        return unavailable()


@router.get("/heads-up")
async def heads_up(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        actor = await require_actor(context, native_token(request))
        if not ({"reports.view", "reports.submit"} & actor.capabilities):
            raise IdentityError("forbidden", "Report access is required.", reason="permission_denied")
        return await call(context.services.stores.heads_up, actor.store_id)
    except IdentityError as error:
        return error_response(error)
    except (psycopg.Error, RuntimeError):
        return unavailable()
