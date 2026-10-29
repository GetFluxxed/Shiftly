"""Real Expo router + tab layout/restoration; fixture accounts, no live data.

Reports and Today use actual screens; other destinations isolate routing from
feature API behavior. Browser checks do not establish iPhone device acceptance.
"""
import http.server
import os
import re
import subprocess
import threading
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


ROOT = Path(__file__).resolve().parents[2]
MOBILE = ROOT / "apps" / "mobile"


@pytest.fixture(scope="session")
def router_bundle(tmp_path_factory):
    output = tmp_path_factory.mktemp("rendered-router") / "router.js"
    node = os.environ.get("NATIVE_TEST_NODE", "node")
    command = [node, str(MOBILE / "tests/rendered/navigation-build.mjs"), str(output)]
    subprocess.run(
        command,
        cwd=MOBILE,
        check=True,
    )
    return output


@pytest.fixture(scope="session")
def router_url(router_bundle):
    class Handler(http.server.SimpleHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/router.js":
                body = router_bundle.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/javascript")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            body = b'''<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>html,body,#root{height:100%;margin:0}#root{display:flex;flex:1}</style></head>
<body><div id="root"></div><script src="/router.js"></script></body></html>'''
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        thread.join()


def assert_route_stays(page: Page, pathname: str):
    heading = "Reports" if pathname == "/reports" else f"Route {pathname}"
    expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()
    expect(page).to_have_url(re.compile(rf".*/{re.escape(pathname.lstrip('/'))}(?:\?.*)?$"))
    page.wait_for_timeout(500)
    expect(page).to_have_url(re.compile(rf".*/{re.escape(pathname.lstrip('/'))}(?:\?.*)?$"))
    expect(page.get_by_role("heading", name=heading, exact=True)).to_be_visible()


def go_from_stub(page: Page, label: str, pathname: str):
    page.get_by_role("button", name=f"Go {label}").click()
    assert_route_stays(page, pathname)


def tab_labels(page: Page):
    return [text.replace("·", "").strip() for text in page.get_by_role("tab").all_text_contents()]


def test_authorized_nested_sections_remain_open_and_visible_tabs_return(page: Page, router_url: str):
    page.goto(f"{router_url}/?role=owner")
    expect(page.get_by_role("button", name="Shift reports")).to_be_visible()
    expect(page).to_have_url(re.compile(r".*/today(?:\?.*)?$"))
    expect(page.get_by_role("tab")).to_have_count(5)
    assert tab_labels(page) == ["Today", "Reports", "Inventory", "Store", "Account"]
    for label in ["Today", "Reports", "Inventory", "Store", "Account"]:
        expect(page.get_by_role("tab", name=label, exact=True)).to_be_visible()
    page.get_by_role("button", name="Shift reports").click()
    assert_route_stays(page, "/reports")
    expect(page.get_by_text("No shift reports", exact=True)).to_be_visible()
    page.get_by_role("button", name="Refresh shift reports", exact=True).click()
    assert_route_stays(page, "/reports")
    page.get_by_role("tab", name="Inventory", exact=True).click()
    assert_route_stays(page, "/inventory")

    for label, pathname in [
        ("Catalog", "/catalog"),
        ("Counts", "/counts"),
        ("Shelves", "/shelves"),
        ("Team", "/team"),
        ("Invoices", "/invoices"),
        ("Incoming", "/incoming"),
    ]:
        go_from_stub(page, label, pathname)

    go_from_stub(page, "Inventory", "/inventory")
    go_from_stub(page, "Account", "/accounts")
    page.get_by_role("button", name="Go Today").click()
    expect(page.get_by_role("button", name="Shift reports")).to_be_visible()
    expect(page).to_have_url(re.compile(r".*/today(?:\?.*)?$"))


def test_production_shortcut_and_role_restriction(page: Page, router_url: str):
    page.goto(f"{router_url}/today?role=owner")
    page.get_by_role("button", name="Production").click()
    assert_route_stays(page, "/production")

    page.goto(f"{router_url}/production?role=production")
    assert_route_stays(page, "/production")
    expect(page.get_by_role("tab")).to_have_count(3)
    assert tab_labels(page) == ["Today", "Production", "Account"]
    for label in ["Today", "Production", "Account"]:
        expect(page.get_by_role("tab", name=label, exact=True)).to_be_visible()
    page.goto(f"{router_url}/reports?role=production")
    expect(page).to_have_url(re.compile(r".*/today(?:\?.*)?$"))

    page.goto(f"{router_url}/today?role=crew")
    expect(page.get_by_role("button", name="Production")).to_have_count(0)
    page.goto(f"{router_url}/production?role=crew")
    expect(page).to_have_url(re.compile(r".*/today(?:\?.*)?$"))


def test_cold_root_restores_the_saved_authorized_section(page: Page, router_url: str):
    page.goto(f"{router_url}/catalog?role=owner")
    assert_route_stays(page, "/catalog")
    page.goto(f"{router_url}/?role=owner")
    assert_route_stays(page, "/catalog")


def test_invoice_home_shortcut_and_role_boundaries(page: Page, router_url: str):
    for role in ['owner', 'manager']:
        page.goto(f"{router_url}/today?role={role}")
        page.get_by_role("button", name="Invoices", exact=True).click()
        assert_route_stays(page, "/invoices")
        go_from_stub(page, "Incoming", "/incoming")
    for role in ['crew', 'production']:
        page.goto(f"{router_url}/today?role={role}")
        expect(page.get_by_role("button", name="Invoices", exact=True)).to_have_count(0)
        for target in ['invoices', 'incoming']:
            page.goto(f"{router_url}/{target}?role={role}")
            expect(page).to_have_url(re.compile(r".*/today(?:\?.*)?$"))
