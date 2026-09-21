#!/usr/bin/env python3
"""Run the development-only FastAPI foundation without changing production startup."""

import uvicorn


if __name__ == "__main__":
    uvicorn.run(
        "backend.shiftly.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=4174,
        reload=False,
    )
