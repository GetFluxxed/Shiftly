from contextlib import asynccontextmanager

from fastapi import FastAPI


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.lifecycle = "started"
    try:
        yield
    finally:
        app.state.lifecycle = "stopped"
