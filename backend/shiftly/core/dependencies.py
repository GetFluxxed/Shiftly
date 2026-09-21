from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

import psycopg
from fastapi import Request

from config import Settings

ConnectionFactory = Callable[[], Any]
WorkerStatusProvider = Callable[[], Mapping[str, Any]]


@dataclass(frozen=True)
class AppContext:
    settings: Settings
    connection_factory: ConnectionFactory
    worker_status_provider: WorkerStatusProvider


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
