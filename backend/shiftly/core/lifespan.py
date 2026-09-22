from contextlib import asynccontextmanager

import anyio
from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lifecycle = "started"
    runtime = getattr(app.state.context, "runtime", None)
    try:
        if runtime is not None:
            await anyio.to_thread.run_sync(runtime.open)
        yield
    finally:
        if runtime is not None:
            await anyio.to_thread.run_sync(runtime.close)
        app.state.lifecycle = "stopped"
