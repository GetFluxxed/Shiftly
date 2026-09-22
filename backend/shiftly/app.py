from fastapi import FastAPI
from starlette.exceptions import HTTPException

from backend.shiftly.api.health import router as health_router
from backend.shiftly.api.static import router as static_router
from backend.shiftly.api.compat import router as compat_router
from backend.shiftly.core.dependencies import (
    AppContext,
    ConnectionFactory,
    PageAccessProvider,
    WorkerStatusProvider,
    default_connection_factory,
    default_worker_status_provider,
)
from backend.shiftly.core.lifespan import lifespan
from backend.shiftly.core.security import SecurityHeadersMiddleware
from backend.shiftly.core.errors import routing_error
from backend.shiftly.core.settings import Settings, load_settings
from backend.shiftly.runtime.application import build_runtime
from backend.shiftly.runtime.composition import build_services
from backend.shiftly.runtime.provider import make_provider


def create_app(
    *,
    settings: Settings | None = None,
    connection_factory: ConnectionFactory | None = None,
    worker_status_provider: WorkerStatusProvider | None = None,
    page_access_provider: PageAccessProvider | None = None,
    provider=None,
) -> FastAPI:
    resolved_settings = settings or load_settings()
    runtime = None
    if connection_factory is None:
        runtime = build_runtime(settings=resolved_settings, provider=provider)
        resolved_connection_factory = runtime.resources.connection
        resolved_worker_status_provider = runtime.worker_status
        services = runtime.services
    else:
        resolved_connection_factory = connection_factory
        resolved_worker_status_provider = worker_status_provider or default_worker_status_provider
        services = build_services(
            settings=resolved_settings,
            connection_factory=resolved_connection_factory,
            provider=provider or make_provider(resolved_settings),
        )
    app = FastAPI(
        title="Shiftly API foundation",
        lifespan=lifespan,
        redirect_slashes=False,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        exception_handlers={HTTPException: routing_error},
    )
    app.state.context = AppContext(
        settings=resolved_settings,
        connection_factory=resolved_connection_factory,
        worker_status_provider=resolved_worker_status_provider,
        services=services,
        runtime=runtime,
        page_access_provider=page_access_provider or _default_page_access_provider,
    )
    app.add_middleware(
        SecurityHeadersMiddleware,
        secure_cookies=resolved_settings.secure_cookies,
    )
    app.include_router(health_router)
    app.include_router(compat_router)
    app.include_router(static_router)
    return app


def _default_page_access_provider(request, page):
    context = request.app.state.context
    manager_token = request.cookies.get("shiftly_manager_session", "")
    crew_token = request.cookies.get("shiftly_crew_session", "")
    if page == "manager.html":
        return bool(context.services.identity.manager_id(manager_token))
    if page == "crew.html":
        return bool(context.services.identity.crew_store(crew_token, manager_token))
    return False
