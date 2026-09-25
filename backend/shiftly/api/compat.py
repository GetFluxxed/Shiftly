"""Reporting compatibility through the same verified principal as account APIs."""
import psycopg
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.shiftly.identity import IdentityError
from backend.shiftly.reports.errors import ReportRejected, WeeklyOverviewBusy
from backend.shiftly.core.dependencies import (
    AppContext, client_key, cookie_token, get_app_context, legacy_credentials, named_account_token,
)
from backend.shiftly.core.request import RequestBodyError, bounded_json
from .accounts import call as _service_call, clear_cookies, error_response as _identity_error, principal as _principal, same_origin, store_precondition

router = APIRouter()


def _error(message, status):
    return JSONResponse(status_code=status, content={"error": message})


def _set_session_cookie(response, context, result, request):
    cookie_name = "shiftly_account_session" if result.role == "account" else (
        "shiftly_manager_session" if result.role == "manager" else "shiftly_crew_session")
    response.set_cookie(cookie_name, result.token, max_age=result.ttl, path="/", httponly=True,
                        samesite="strict", secure=context.settings.secure_cookies)
    for old_cookie in ("shiftly_account_session", "shiftly_manager_session", "shiftly_crew_session"):
        present = (named_account_token(request) is not None if old_cookie == "shiftly_account_session"
                   else bool(cookie_token(request, old_cookie)))
        if old_cookie != cookie_name and (result.role == "account" or present):
            response.delete_cookie(old_cookie, path="/", secure=context.settings.secure_cookies,
                                   httponly=True, samesite="strict")
    return response


async def _optional_principal(context, request):
    try:
        return await _principal(context, request)
    except IdentityError:
        # Legacy status/pages report unauthenticated rather than expose a
        # different cookie's identity. Protected routes below still deny access.
        return None


@router.get("/api/auth/status")
async def auth_status(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if named_account_token(request) is not None:
            actor = resolved.actor if resolved and resolved.named else None
            return {"authenticated": bool(actor),
                    "role": ("crew" if actor.role == "crew" else "manager") if actor else None,
                    "managerName": actor.display_name if actor and actor.role != "crew" else None,
                    "actor": actor.as_dict() if actor else None}
        return {"authenticated": bool(resolved),
                "role": "manager" if resolved and resolved.can_manage else "crew" if resolved else None,
                "managerName": await _service_call(context.services.stores.manager_username, resolved.manager_id)
                               if resolved and resolved.can_manage else None}
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)


@router.post("/api/auth/login")
async def login(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        fields = await bounded_json(request, max_body=10_000, invalid_message="Invalid login request.")
        result = await _service_call(context.services.identity.login_payload, fields, client_key=client_key(request))
    except RequestBodyError:
        return _error("Invalid login request.", 400)
    except IdentityError as error:
        return _identity_error(error)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)
    return _set_session_cookie(JSONResponse(status_code=200, content=result.response), context, result, request)


@router.post("/api/auth/signup")
@router.post("/api/auth/add-manager")
async def invitation_required(request: Request):
    return _error("Accounts require an invitation. Ask your store administrator.", 403)


@router.post("/api/auth/logout")
async def logout(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        await _service_call(context.services.identity.logout, **legacy_credentials(request))
        account_token = named_account_token(request)
        if account_token is not None:
            await _service_call(context.services.accounts.logout, account_token)
        response = JSONResponse(content={"authenticated": False})
        if account_token is not None:
            return clear_cookies(response, context)
        # Keep the exact older two-cookie response when no named cookie exists.
        for name in ("shiftly_manager_session", "shiftly_crew_session"):
            response.delete_cookie(name, path="/", secure=context.settings.secure_cookies, httponly=True, samesite="strict")
        return response
    except IdentityError as error:
        return _identity_error(error)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)


@router.get("/api/reports")
async def reports(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if not resolved or not resolved.can_manage:
            return _error("Manager authentication required.", 401)
        if resolved.named:
            value = await _service_call(context.services.reports.list_for_actor, named_account_token(request), context.services.accounts)
        else:
            value = await _service_call(context.services.reports.list_for_manager, resolved.manager_id)
        return {"reports": value}
    except IdentityError as error:
        return _identity_error(error)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)
    except RuntimeError as error:
        return _error(str(error), 503)


@router.post("/api/reports", status_code=202)
async def submit_report(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if not resolved or (resolved.named and "reports.submit" not in resolved.actor.capabilities):
            return _error("Crew sign-in required.", 401)
        if context.services.admission.report_limited(client_key(request)):
            return _error("Too many submissions. Try again later.", 429)
        fields = await bounded_json(request, max_body=100_000, invalid_message="Invalid report format.")
        if resolved.named:
            same_origin(request)
            store_precondition(fields, resolved)
            _, created_at = await _service_call(context.services.submission.submit, resolved.store_id, fields,
                                                actor_token=named_account_token(request), accounts=context.services.accounts)
        else:
            _, created_at = await _service_call(context.services.submission.submit, resolved.store_id, fields,
                                                legacy_credentials=legacy_credentials(request))
        return {"date": created_at.isoformat(), "status": "pending"}
    except IdentityError as error:
        return _identity_error(error)
    except RequestBodyError as error:
        return _error(str(error), 400)
    except ReportRejected as error:
        return _error(error.reason, 422)
    except ValueError as error:
        return _error(str(error), 400)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)
    except RuntimeError as error:
        return _error(str(error), 503)


@router.get("/api/heads-up")
async def get_heads_up(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if not resolved or (resolved.named and not resolved.can_manage and "reports.submit" not in resolved.actor.capabilities):
            return _error("Sign-in required.", 401)
        return await _service_call(context.services.stores.heads_up, resolved.store_id)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)


@router.post("/api/heads-up")
async def save_heads_up(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if not resolved or not resolved.can_manage:
            return _error("Manager sign-in required.", 401)
        fields = await bounded_json(request, max_body=100_000, invalid_message="Invalid report format.")
        if resolved.named:
            same_origin(request)
            store_precondition(fields, resolved)
            return await _service_call(context.services.stores.save_heads_up, resolved.store_id, fields.get("message"),
                                       actor_token=named_account_token(request), accounts=context.services.accounts)
        return await _service_call(context.services.stores.save_heads_up, resolved.store_id, fields.get("message"),
                                   legacy_credentials=legacy_credentials(request))
    except IdentityError as error:
        return _identity_error(error)
    except (RequestBodyError, ValueError) as error:
        return _error(str(error), 400)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)
    except RuntimeError as error:
        return _error(str(error), 503)


@router.get("/api/managers")
async def managers(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if not resolved or not resolved.can_manage:
            return _error("Manager sign-in required.", 401)
        return {"managers": await _service_call(context.services.accounts.report_managers, named_account_token(request))}
    except IdentityError as error:
        return _identity_error(error)
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)


@router.get("/api/weekly-overview")
async def weekly_overview(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        resolved = await _optional_principal(context, request)
        if not resolved or not resolved.can_manage:
            return _error("Manager sign-in required.", 401)
        return await _service_call(context.services.weekly.overview, resolved.store_id)
    except WeeklyOverviewBusy:
        return JSONResponse(status_code=202, content={"status": "pending", "retryAfter": 3})
    except psycopg.Error:
        return _error("Service is temporarily unavailable.", 503)
    except (RuntimeError, ValueError) as error:
        return _error(str(error), 503)
