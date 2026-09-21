from collections.abc import Mapping
from typing import Any, Annotated

import psycopg
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from backend.shiftly.core.dependencies import AppContext, get_app_context

router = APIRouter()


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    status: str
    openaiConfigured: bool
    databaseConfigured: bool
    secureCookies: bool
    worker: Mapping[str, Any]


def _database_is_ready(context: AppContext) -> bool:
    try:
        with context.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                return cursor.fetchone() == (1,)
    except (RuntimeError, psycopg.Error):
        return False


def _degraded_worker() -> dict[str, Any]:
    return {
        "status": "degraded",
        "state": "unavailable",
        "running": False,
        "lastPollAgeSeconds": None,
        "lastCompletionAgeSeconds": None,
        "completedJobs": 0,
        "consecutiveErrors": 0,
    }


def _worker_status(context: AppContext) -> Mapping[str, Any]:
    try:
        status = context.worker_status_provider()
    except (RuntimeError, ConnectionError, TimeoutError):
        return _degraded_worker()
    if not isinstance(status, Mapping) or not isinstance(status.get("status"), str):
        return _degraded_worker()
    return status


@router.get("/api/health")
def health(context: Annotated[AppContext, Depends(get_app_context)]):
    database_ok = _database_is_ready(context)
    payload = HealthResponse(
        status="ok" if database_ok else "degraded",
        openaiConfigured=bool(context.settings.openai_api_key),
        databaseConfigured=database_ok,
        secureCookies=context.settings.secure_cookies,
        worker=_worker_status(context),
    )
    return JSONResponse(
        status_code=200 if database_ok else 503,
        content=payload.model_dump(),
    )


@router.get("/api/health/worker")
def worker_health(context: Annotated[AppContext, Depends(get_app_context)]):
    payload = dict(_worker_status(context))
    return JSONResponse(
        status_code=200 if payload.get("status") == "ok" else 503,
        content=payload,
    )
