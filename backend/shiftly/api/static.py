from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse

from backend.shiftly.core.dependencies import AppContext, get_app_context

router = APIRouter()
ROOT = Path(__file__).resolve().parents[3]
PUBLIC_ASSETS = {
    "/": ROOT / "index.html",
    "/index.html": ROOT / "index.html",
    "/about.html": ROOT / "about.html",
    "/app.js": ROOT / "app.js",
    "/auth.js": ROOT / "auth.js",
    "/manager.js": ROOT / "manager.js",
    "/accounts.js": ROOT / "accounts.js",
    "/activate.js": ROOT / "activate.js",
    "/activate.html": ROOT / "activate.html",
    "/inventory.js": ROOT / "inventory.js",
    "/styles.css": ROOT / "styles.css",
}
PROTECTED_PAGES = {
    "/crew.html": "crew.html",
    "/manager.html": "manager.html",
    "/accounts.html": "accounts.html",
    "/inventory.html": "inventory.html",
}


def _file_response(path: Path):
    if path.resolve().parent != ROOT.resolve() or not path.is_file():
        raise HTTPException(status_code=404, detail="Not found.")
    return FileResponse(path)


def _protected_page(request: Request, path: str, context: AppContext):
    provider = context.page_access_provider
    if provider is None or not provider(request, path):
        return RedirectResponse("/", status_code=302)
    return _file_response(ROOT / path)


@router.get("/", include_in_schema=False)
@router.get("/index.html", include_in_schema=False)
@router.get("/about.html", include_in_schema=False)
@router.get("/app.js", include_in_schema=False)
@router.get("/auth.js", include_in_schema=False)
@router.get("/manager.js", include_in_schema=False)
@router.get("/accounts.js", include_in_schema=False)
@router.get("/activate.js", include_in_schema=False)
@router.get("/activate.html", include_in_schema=False)
@router.get("/inventory.js", include_in_schema=False)
@router.get("/styles.css", include_in_schema=False)
def public_asset(request: Request, context: Annotated[AppContext, Depends(get_app_context)]):
    return _file_response(PUBLIC_ASSETS[request.url.path])


@router.get("/crew.html", include_in_schema=False)
@router.get("/manager.html", include_in_schema=False)
@router.get("/accounts.html", include_in_schema=False)
@router.get("/inventory.html", include_in_schema=False)
def protected_page(request: Request, context: Annotated[AppContext, Depends(get_app_context)]):
    return _protected_page(request, PROTECTED_PAGES[request.url.path], context)
