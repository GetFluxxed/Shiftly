from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI

from backend.shiftly.api.health import router as health_router
from backend.shiftly.core.dependencies import (
    AppContext,
    ConnectionFactory,
    WorkerStatusProvider,
    default_connection_factory,
    default_worker_status_provider,
)
from backend.shiftly.core.lifespan import lifespan
from backend.shiftly.core.security import SecurityHeadersMiddleware
from backend.shiftly.core.settings import Settings, load_settings


def create_app(
    *,
    settings: Settings | None = None,
    connection_factory: ConnectionFactory | None = None,
    worker_status_provider: WorkerStatusProvider | None = None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    resolved_connection_factory = connection_factory or default_connection_factory(resolved_settings)
    resolved_worker_status_provider = worker_status_provider or default_worker_status_provider
    app = FastAPI(
        title="Shiftly API foundation",
        lifespan=lifespan,
    )
    app.state.context = AppContext(
        settings=resolved_settings,
        connection_factory=resolved_connection_factory,
        worker_status_provider=resolved_worker_status_provider,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        secure_cookies=resolved_settings.secure_cookies,
    )
    app.include_router(health_router)
    return app
