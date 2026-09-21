"""Runtime bundle consumed by a transport's lifespan and dependency adapters."""

from dataclasses import dataclass

from backend.shiftly.jobs.status import DatabaseWorkerStatus
from .composition import build_services
from .database import DatabaseResources
from .migrate import require_schema, schema_status
from .provider import make_provider


@dataclass
class ApplicationRuntime:
    resources: DatabaseResources
    services: object
    worker_status: DatabaseWorkerStatus

    def open(self):
        self.resources.open()
        try:
            require_schema(self.resources.connection)
        except BaseException:
            self.resources.close()
            raise
        return self

    def close(self):
        self.resources.close()

    def schema_status(self):
        return schema_status(self.resources.connection)


def build_runtime(*, settings, provider=None):
    """Construct without I/O; call open()/close() off the async event loop."""
    resources = DatabaseResources(settings)
    services = build_services(settings=settings, connection_factory=resources.connection,
                              weekly_connection_factory=resources.weekly_connection,
                              provider=provider if provider is not None else make_provider(settings))
    return ApplicationRuntime(resources, services,
                              DatabaseWorkerStatus(resources.connection, stale_seconds=settings.worker_stale_seconds))
