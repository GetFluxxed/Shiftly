"""Preserve the legacy server's routing failures without invoking its handler."""

import html
from http import HTTPStatus
from http.server import DEFAULT_ERROR_MESSAGE

from fastapi.responses import HTMLResponse, JSONResponse


def legacy_http_error(status, *, message=None, head=False):
    code = HTTPStatus(status)
    body = DEFAULT_ERROR_MESSAGE % {
        "code": status,
        "message": html.escape(message or code.phrase, quote=False),
        "explain": html.escape(code.description, quote=False),
    }
    return HTMLResponse(
        "" if head else body, status_code=status,
        headers={"Content-Length": str(len(body.encode("utf-8")))},
    )


async def routing_error(request, error):
    if error.status_code not in {404, 405}:
        return JSONResponse({"detail": error.detail}, status_code=error.status_code,
                            headers=error.headers)
    if request.method not in {"GET", "POST"}:
        return legacy_http_error(501, message=f"Unsupported method ({request.method!r})",
                                 head=request.method == "HEAD")
    if request.method == "POST":
        return JSONResponse({"error": "Not found."}, status_code=404)
    return legacy_http_error(404)
