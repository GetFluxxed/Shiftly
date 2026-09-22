"""Legacy browser contracts, exercised unchanged against both HTTP servers."""

from http.cookies import SimpleCookie

import pytest


@pytest.mark.parametrize("raw", [b"", b"{", b"[]", b"null", b"\xff", b"x" * 10_001],
                         ids=["empty", "broken-json", "array", "null", "non-utf8", "oversize"])
def test_login_rejects_invalid_body_consistently(api, raw):
    response = api.request("POST", "/api/auth/login", raw=raw)
    assert response.status == 400
    assert response.json() == {"error": "Invalid login request."}


@pytest.mark.parametrize("path", ["/api/auth/signup", "/api/auth/add-manager", "/api/reports", "/api/heads-up"])
@pytest.mark.parametrize("raw,message", [
    (b"", "Request is empty or too large."),
    (b"x" * 100_001, "Request is empty or too large."),
    (b"{", "Invalid report format."),
    (b"[]", "Invalid report format."),
    (b"\xff", "Invalid report format."),
], ids=["empty", "oversize", "broken-json", "array", "non-utf8"])
def test_json_request_errors_are_stable(api, workspace, path, raw, message):
    response = api.request("POST", path, raw=raw, cookie=workspace["manager_cookie"])
    assert response.status == 400
    assert response.json() == {"error": message}


@pytest.mark.parametrize("path", ["/api/reports", "/api/heads-up"])
def test_authorization_precedes_body_validation(api, path):
    response = api.request("POST", path, raw=b"{")
    assert response.status == 401


@pytest.mark.parametrize("path", ["/missing", "/api/missing", "/api/auth/login", "/api/reports/", "/docs", "/openapi.json"])
def test_unknown_get_and_post_only_routes_keep_404(api, path):
    response = api.request("GET", path)
    assert response.status == 404
    assert dict((key.lower(), value) for key, value in response.headers)["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/api/missing", "/api/managers", "/api/auth/login/", "/"])
def test_unknown_post_and_get_only_routes_keep_json_404(api, path):
    response = api.request("POST", path, payload={})
    assert response.status == 404
    assert response.json() == {"error": "Not found."}


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def test_unsupported_methods_keep_legacy_status(api, method):
    response = api.request(method, "/api/reports")
    assert response.status == 501
    if method == "HEAD":
        assert response.body == b""
    else:
        assert b"Unsupported method" in response.body


def test_session_cookie_attributes_and_security_headers(api, workspace):
    response = api.request("POST", "/api/auth/login", payload={
        "storeCode": workspace["store_code"], "password": workspace["manager_password"],
    })
    assert response.status == 200
    cookies = SimpleCookie()
    for name, value in response.headers:
        if name.lower() == "set-cookie":
            cookies.load(value)
    cookie = cookies["shiftly_manager_session"]
    assert cookie["httponly"] and cookie["path"] == "/"
    assert cookie["samesite"].lower() == "strict" and int(cookie["max-age"]) == 28800
    headers = {key.lower(): value for key, value in response.headers}
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in headers["content-security-policy"]
    assert api.request("GET", "/api/reports", cookie=workspace["manager_cookie"]).status == 200
