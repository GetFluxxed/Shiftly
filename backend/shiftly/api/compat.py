import anyio
import psycopg
from functools import partial
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.shiftly.identity import IdentityError
from backend.shiftly.reports.errors import ReportRejected, WeeklyOverviewBusy
from backend.shiftly.core.dependencies import AppContext, client_key, cookie_token, get_app_context
from backend.shiftly.core.request import RequestBodyError, bounded_json

router = APIRouter()

ERROR_STATUS = {
    "invalid": 400,
    "unauthenticated": 401,
    "forbidden": 403,
    "not_found": 404,
    "conflict": 409,
    "limited": 429,
    "unavailable": 503,
}


def _error(message, status):
    return JSONResponse(status_code=status, content={"error": message})


def _identity_error(error):
    return _error(str(error), ERROR_STATUS.get(error.code, 503))


def _set_session_cookie(response, context, result):
    cookie_name = (
        "shiftly_manager_session"
        if result.role == "manager"
        else "shiftly_crew_session"
    )
    response.set_cookie(
        cookie_name,
        result.token,
        max_age=result.ttl,
        path="/",
        httponly=True,
        samesite="strict",
        secure=context.settings.secure_cookies,
    )
    return response


def _expire_session_cookies(response, context):
    for cookie_name in ("shiftly_manager_session", "shiftly_crew_session"):
        response.delete_cookie(
            cookie_name,
            path="/",
            secure=context.settings.secure_cookies,
            httponly=True,
            samesite="strict",
        )
    return response


def _manager_store(context, request):
    manager_token = cookie_token(request, "shiftly_manager_session")
    manager_id = context.services.identity.manager_id(manager_token)
    if not manager_id:
        return None, None
    return manager_id, context.services.identity.selected_store(manager_token, manager_id)


async def _service_call(function, *args, **kwargs):
    return await anyio.to_thread.run_sync(partial(function, *args, **kwargs))


@router.get("/api/auth/status")
async def auth_status(request: Request, context: AppContext = Depends(get_app_context)):
    manager_token = cookie_token(request, "shiftly_manager_session")
    crew_token = cookie_token(request, "shiftly_crew_session")
    manager_id = await _service_call(context.services.identity.manager_id, manager_token)
    crew_store_id = await _service_call(context.services.identity.crew_store, crew_token, manager_token)
    return {
        "authenticated": bool(manager_id or crew_store_id),
        "role": "manager" if manager_id else "crew" if crew_store_id else None,
        "managerName": (
            await _service_call(context.services.stores.manager_username, manager_id)
            if manager_id
            else None
        ),
    }


@router.post("/api/auth/login")
async def login(request: Request, context: AppContext = Depends(get_app_context)):
    try:
        fields = await bounded_json(
            request, max_body=10_000, invalid_message="Invalid login request."
        )
        result = await _service_call(
            context.services.identity.login_payload,
            fields,
            client_key=client_key(request),
        )
    except RequestBodyError:
        return _error("Invalid login request.", 400)
    except IdentityError as error:
        return _identity_error(error)
    return _set_session_cookie(
        JSONResponse(status_code=200, content=result.response), context, result
    )


async def _account_creation(request, context, *, action):
    try:
        await _service_call(
            context.services.identity.admit_account_creation,
            client_key(request),
            action=action,
        )
        fields = await bounded_json(request, max_body=100_000, invalid_message="Invalid report format.")
        creator = (
            context.services.identity.signup
            if action == "signup"
            else context.services.identity.add_manager
        )
        result = await _service_call(creator, fields)
    except RequestBodyError as error:
        return _error(str(error), 400)
    except IdentityError as error:
        return _identity_error(error)
    return _set_session_cookie(
        JSONResponse(status_code=201, content=result.response), context, result
    )


@router.post("/api/auth/signup")
async def signup(request: Request, context: AppContext = Depends(get_app_context)):
    return await _account_creation(request, context, action="signup")


@router.post("/api/auth/add-manager")
async def add_manager(request: Request, context: AppContext = Depends(get_app_context)):
    return await _account_creation(request, context, action="add_manager")


@router.post("/api/auth/logout")
async def logout(request: Request, context: AppContext = Depends(get_app_context)):
    await _service_call(
        context.services.identity.logout,
        cookie_token(request, "shiftly_manager_session"),
        cookie_token(request, "shiftly_crew_session"),
    )
    return _expire_session_cookies(
        JSONResponse(status_code=200, content={"authenticated": False}), context
    )


@router.get("/api/reports")
async def reports(request: Request, context: AppContext = Depends(get_app_context)):
    manager_id, _ = await _service_call(_manager_store, context, request)
    if not manager_id:
        return _error("Manager authentication required.", 401)
    try:
        value = await _service_call(context.services.reports.list_for_manager, manager_id)
    except RuntimeError as error:
        return _error(str(error), 503)
    return {"reports": value}


@router.post("/api/reports", status_code=202)
async def submit_report(request: Request, context: AppContext = Depends(get_app_context)):
    store_id = await _service_call(
        context.services.identity.crew_store,
        cookie_token(request, "shiftly_crew_session"),
        cookie_token(request, "shiftly_manager_session"),
    )
    if not store_id:
        return _error("Crew sign-in required.", 401)
    if context.services.admission.report_limited(client_key(request)):
        return _error("Too many submissions. Try again later.", 429)
    try:
        fields = await bounded_json(request, max_body=100_000, invalid_message="Invalid report format.")
        report_id, created_at = await _service_call(
            context.services.submission.submit, store_id, fields
        )
    except RequestBodyError as error:
        return _error(str(error), 400)
    except ReportRejected as error:
        return _error(error.reason, 422)
    except ValueError as error:
        return _error(str(error), 400)
    except RuntimeError as error:
        return _error(str(error), 503)
    return {"date": created_at.isoformat(), "status": "pending"}


@router.get("/api/heads-up")
async def get_heads_up(request: Request, context: AppContext = Depends(get_app_context)):
    manager_id, store_id = await _service_call(_manager_store, context, request)
    if not store_id:
        store_id = await _service_call(
            context.services.identity.crew_store,
            cookie_token(request, "shiftly_crew_session"),
            cookie_token(request, "shiftly_manager_session"),
        )
    if not store_id:
        return _error("Sign-in required.", 401)
    return await _service_call(context.services.stores.heads_up, store_id)


@router.post("/api/heads-up")
async def save_heads_up(request: Request, context: AppContext = Depends(get_app_context)):
    _, store_id = await _service_call(_manager_store, context, request)
    if not store_id:
        return _error("Manager sign-in required.", 401)
    try:
        fields = await bounded_json(request, max_body=100_000, invalid_message="Invalid report format.")
        return await _service_call(
            context.services.stores.save_heads_up, store_id, fields.get("message")
        )
    except RequestBodyError as error:
        return _error(str(error), 400)
    except (RuntimeError, ValueError) as error:
        return _error(str(error), 503 if isinstance(error, RuntimeError) else 400)


@router.get("/api/managers")
async def managers(request: Request, context: AppContext = Depends(get_app_context)):
    _, store_id = await _service_call(_manager_store, context, request)
    if not store_id:
        return _error("Manager sign-in required.", 401)
    return {"managers": await _service_call(context.services.stores.manager_accounts, store_id)}


@router.get("/api/weekly-overview")
async def weekly_overview(request: Request, context: AppContext = Depends(get_app_context)):
    _, store_id = await _service_call(_manager_store, context, request)
    if not store_id:
        return _error("Manager sign-in required.", 401)
    try:
        return await _service_call(context.services.weekly.overview, store_id)
    except WeeklyOverviewBusy:
        return JSONResponse(status_code=202, content={"status": "pending", "retryAfter": 3})
    except (RuntimeError, ValueError, psycopg.Error) as error:
        return _error(str(error), 503)
