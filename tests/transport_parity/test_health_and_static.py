from http.client import HTTPConnection

from backend.shiftly.app import create_app
from config import Settings
from fastapi.testclient import TestClient


def legacy_get(httpd, path):
    connection = HTTPConnection(*httpd.server_address, timeout=5)
    try:
        connection.request("GET", path)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_health_has_compatible_status_and_stable_fields(transport_clients):
    fastapi_client, legacy_httpd = transport_clients
    legacy_status, _, legacy_body = legacy_get(legacy_httpd, "/api/health")
    fastapi_response = fastapi_client.get("/api/health")

    assert fastapi_response.status_code == legacy_status == 200
    legacy_payload = __import__("json").loads(legacy_body)
    fastapi_payload = fastapi_response.json()
    for field in ("status", "openaiConfigured", "databaseConfigured", "secureCookies"):
        assert fastapi_payload[field] == legacy_payload[field]
    assert fastapi_payload["worker"]["status"] == legacy_payload["worker"]["status"]


def test_public_assets_match_the_legacy_surface(transport_clients):
    fastapi_client, legacy_httpd = transport_clients
    for path in ("/", "/index.html", "/about.html", "/styles.css"):
        legacy_status, _, legacy_body = legacy_get(legacy_httpd, path)
        fastapi_response = fastapi_client.get(path, follow_redirects=False)
        assert fastapi_response.status_code == legacy_status == 200
        assert fastapi_response.content == legacy_body


def test_protected_pages_redirect_without_an_access_provider(transport_clients):
    fastapi_client, legacy_httpd = transport_clients
    for path in ("/crew.html", "/manager.html"):
        legacy_status, legacy_headers, _ = legacy_get(legacy_httpd, path)
        fastapi_response = fastapi_client.get(path, follow_redirects=False)
        assert fastapi_response.status_code == legacy_status == 302
        assert fastapi_response.headers["location"] == legacy_headers["Location"]


def test_protected_page_access_is_explicitly_injected():
    app = create_app(
        settings=Settings(secure_cookies=False),
        connection_factory=lambda: (_ for _ in ()).throw(RuntimeError("unused")),
        worker_status_provider=lambda: {"status": "degraded"},
        page_access_provider=lambda request, page: page == "manager.html",
    )
    with TestClient(app) as client:
        allowed = client.get("/manager.html", follow_redirects=False)
        denied = client.get("/crew.html", follow_redirects=False)

    assert allowed.status_code == 200
    assert denied.status_code == 302


def test_private_and_traversal_paths_are_not_served(transport_clients):
    fastapi_client, legacy_httpd = transport_clients
    for path in ("/.env", "/server.py", "/%2e%2e/server.py"):
        legacy_status, _, _ = legacy_get(legacy_httpd, path)
        fastapi_response = fastapi_client.get(path, follow_redirects=False)
        assert legacy_status == fastapi_response.status_code == 404


def test_security_headers_cover_success_redirect_and_error(transport_clients):
    fastapi_client, _ = transport_clients
    for path in ("/", "/manager.html", "/private.txt"):
        response = fastapi_client.get(path)
        assert response.headers["x-content-type-options"] == "nosniff"
        assert response.headers["x-frame-options"] == "DENY"
        assert response.headers["referrer-policy"] == "no-referrer"
        assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"
        assert response.headers["content-security-policy"].startswith("default-src 'self'")
