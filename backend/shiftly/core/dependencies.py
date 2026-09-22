from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from fastapi import Request

from config import Settings

ConnectionFactory = Callable[[], Any]
WorkerStatusProvider = Callable[[], Mapping[str, Any]]
PageAccessProvider = Callable[[Any, str], bool]


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    connection_factory: ConnectionFactory
    worker_status_provider: WorkerStatusProvider
    services: Any
    runtime: Any = None
    page_access_provider: PageAccessProvider | None = None


def default_connection_factory(settings: Settings) -> ConnectionFactory:
    def connect():
        if not settings.database_url:
            raise RuntimeError("DATABASE_URL is not configured.")
        return psycopg.connect(settings.database_url)

    return connect


def default_worker_status_provider() -> Mapping[str, Any]:
    from reporting import worker_status

    return worker_status()


def get_app_context(request: Request) -> AppContext:
    return request.app.state.context


def client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def cookie_token(request: Request, name: str) -> str:
    values = []
    for item in ";".join(request.headers.getlist("cookie")).split(";"):
        key, separator, value = item.strip().partition("=")
        if separator and key == name:
            values.append(value)
    return values[0] if values else ""


def named_account_token(request: Request) -> str | None:
    values = []
    for item in ";".join(request.headers.getlist("cookie")).split(";"):
        key, separator, value = item.strip().partition("=")
        if key == "shiftly_account_session":
            values.append(value if separator else "")
    if not values:
        return None
    if len(values) != 1:
        return ""
    return values[0]


def identity_credentials(request: Request) -> dict:
    """Preserve absence versus an invalid named cookie at every entry point."""
    return {
        "account_token": named_account_token(request),
        "manager_token": cookie_token(request, "shiftly_manager_session"),
        "crew_token": cookie_token(request, "shiftly_crew_session"),
    }


def legacy_credentials(request: Request) -> dict:
    return {
        "manager_token": cookie_token(request, "shiftly_manager_session"),
        "crew_token": cookie_token(request, "shiftly_crew_session"),
    }
