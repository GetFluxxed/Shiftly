"""Every native route loaded through the real Expo Router with synthetic data.

This is web-history evidence for Expo Router and the real screen modules. It does
not replace the screen-specific workbench tests or physical iOS stack testing.
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
PRODUCT = "11111111-1111-4111-8111-111111111111"
COUNT = RECIPE = "22222222-2222-4222-8222-222222222222"
SHELF = INVOICE = "33333333-3333-4333-8333-333333333333"
LINE = LOG = "44444444-4444-4444-8444-444444444444"


@pytest.fixture(scope="session")
def full_router_bundle(tmp_path_factory):
    output = tmp_path_factory.mktemp("full-router") / "router.js"
    subprocess.run([
        os.environ.get("NATIVE_TEST_NODE", "node"),
        str(MOBILE / "tests/rendered/navigation-build.mjs"), str(output), "--full",
    ], cwd=MOBILE, check=True)
    return output


@pytest.fixture(scope="session")
def full_router_url(full_router_bundle):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.split("?", 1)[0] == "/router.js":
                body, kind = full_router_bundle.read_bytes(), "text/javascript"
            else:
                body, kind = (b"<!doctype html><html><head><meta name=viewport "
                    b"content='width=device-width,initial-scale=1'><style>html,body,#root{height:100%;margin:0}#root{display:flex;flex:1}</style></head><body>"
                    b"<div id=root></div><script src=/router.js></script></body></html>"), "text/html"
            self.send_response(200); self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def log_message(self, *_args): pass
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
    try: yield f"http://127.0.0.1:{server.server_port}"
    finally: server.shutdown(); server.server_close(); thread.join(timeout=5)


ROUTES = [
    "/today", "/reports", "/inventory", "/accounts", "/store", "/heads-up", "/time-tracking",
    "/catalog", "/catalog/new", "/catalog/scan", "/catalog/saved-scans", f"/catalog/{PRODUCT}", f"/catalog/packages/{PRODUCT}",
    "/shelves", f"/shelves/{SHELF}", "/stock", f"/stock/{PRODUCT}", "/counts", "/counts/history",
    f"/counts/{COUNT}", f"/counts/{COUNT}/line/{LINE}", f"/counts/{COUNT}/review",
    "/production", "/production/run", "/production/review", "/production/recipes", "/production/recipes/new",
    f"/production/recipes/{RECIPE}", "/production/logs", f"/production/logs/{LOG}",
    "/invoices", f"/invoices/{INVOICE}", f"/invoices/{INVOICE}/photo", "/incoming",
    "/team", "/team/invite", "/team/assign", "/team/build", "/team/access", "/team/2",
    "/owner", "/owner/2", "/owner/cutover",
]


def test_generated_context_tracks_every_app_route(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/today?role=owner")
    expected = sorted("./" + path.relative_to(MOBILE / "app").as_posix()
                      for path in (MOBILE / "app").rglob("*.tsx"))
    assert page.evaluate("window.__shiftlyRouteKeys.slice().sort()") == expected


def test_audited_route_cases_cover_every_screen_file():
    values = {"productId": PRODUCT, "shelfId": SHELF, "countId": COUNT, "lineId": LINE,
              "invoiceId": INVOICE, "recipeId": RECIPE, "logId": LOG, "userId": "2"}
    authenticated = set()
    public = set()
    for path in (MOBILE / "app").rglob("*.tsx"):
        relative = path.relative_to(MOBILE / "app").as_posix()
        if relative.endswith("_layout.tsx"): continue
        route = "/" + relative.removesuffix(".tsx")
        route = route.replace("/(app)", "").removesuffix("/index") or "/"
        for key, value in values.items(): route = route.replace(f"[{key}]", value)
        (public if route in {"/", "/sign-in", "/activate"} else authenticated).add(route)
    assert authenticated == set(ROUTES)
    assert public == {"/", "/sign-in", "/activate"}


@pytest.mark.parametrize("route", ROUTES)
def test_every_authenticated_screen_is_a_real_deep_link(page: Page, full_router_url: str, route: str):
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.goto(f"{full_router_url}{route}?role=owner")
    expect(page).to_have_url(re.compile(rf"{re.escape(route)}(?:\?.*)?$"))
    expect(page.locator("#root"), message="; ".join(errors)).not_to_be_empty()
    expect(page.get_by_role("heading").first).to_be_visible()
    page.wait_for_timeout(100)
    assert errors == []
    assert page.evaluate("window.__unexpectedFixtureRequests") == []


@pytest.mark.parametrize("route", ["/production", "/invoices", "/incoming", "/time-tracking"])
def test_hidden_crew_deep_links_return_to_today(page: Page, full_router_url: str, route: str):
    page.goto(f"{full_router_url}{route}?role=crew")
    expect(page).to_have_url(re.compile(r"/today(?:\?.*)?$"))


@pytest.mark.parametrize("route", ["/team", "/owner"])
def test_administration_deep_link_keeps_route_but_renders_crew_denial(page: Page, full_router_url: str, route: str):
    page.goto(f"{full_router_url}{route}?role=crew")
    expect(page).to_have_url(re.compile(rf"{route}(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="Access is limited", exact=True)).to_be_visible()


def test_browser_back_preserves_the_origin_in_real_expo_history(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/today?role=owner")
    page.get_by_role("button", name="Shift reports", exact=True).click()
    expect(page).to_have_url(re.compile(r"/reports(?:\?.*)?$"))
    page.go_back()
    expect(page).to_have_url(re.compile(r"/today(?:\?.*)?$"))
    expect(page.get_by_role("button", name="Shift reports", exact=True)).to_be_visible()


def test_cold_root_restores_last_real_route(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/time-tracking?role=owner")
    expect(page).to_have_url(re.compile(r"/time-tracking(?:\?.*)?$"))
    page.reload()
    expect(page).to_have_url(re.compile(r"/time-tracking(?:\?.*)?$"))
    page.goto(f"{full_router_url}/?role=owner")
    expect(page).to_have_url(re.compile(r"/time-tracking(?:\?.*)?$"))


def test_public_sign_in_activate_and_back_use_real_router(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/sign-in?auth=signedout")
    expect(page.get_by_role("heading", name="Sign in to Shiftly", exact=True)).to_be_visible()
    page.get_by_role("button", name="Activate account or reset password", exact=True).click()
    expect(page).to_have_url(re.compile(r"/activate(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="Activate account", exact=True)).to_be_visible()
    page.get_by_role("button", name="Back to sign in", exact=True).click()
    expect(page).to_have_url(re.compile(r"/sign-in(?:\?.*)?$"))


def test_signed_in_activation_keeps_current_account_and_returns_today(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/activate?role=owner")
    expect(page.get_by_role("button", name="Keep my current account", exact=True)).to_be_visible()
    page.get_by_role("button", name="Keep my current account", exact=True).click()
    expect(page).to_have_url(re.compile(r"/today(?:\?.*)?$"))


@pytest.mark.parametrize("route,label,parent", [
    ("/catalog/new", "Back to catalog", "/catalog"), ("/catalog/scan", "Back to catalog", "/catalog"),
    ("/catalog", "Back to inventory", "/inventory"),
    (f"/catalog/{PRODUCT}", "Back to catalog", "/catalog"),
    (f"/catalog/packages/{PRODUCT}", "Back to product", f"/catalog/{PRODUCT}"),
    ("/shelves", "Back to inventory", "/inventory"), (f"/shelves/{SHELF}", "Back to Open Shelves", "/shelves"),
    ("/stock", "Back to inventory", "/inventory"), (f"/stock/{PRODUCT}", "Back to current inventory", "/stock"),
    ("/counts", "Back to inventory", "/inventory"), ("/counts/history", "Back to count inventory", "/counts"),
    (f"/counts/{COUNT}", "Back to count inventory", "/counts"), (f"/counts/{COUNT}/review", "Back to count entries", f"/counts/{COUNT}"),
    (f"/counts/{COUNT}/line/{LINE}", "Back to count entries", f"/counts/{COUNT}"),
    ("/production", "Back to Today", "/today"), ("/production/run", "Back to production", "/production"),
    ("/production/review", "Back to production run", "/production/run"),
    ("/production/recipes", "Back to production", "/production"),
    (f"/production/recipes/{RECIPE}", "Back to recipes", "/production/recipes"),
    ("/production/logs", "Back to production", "/production"), (f"/production/logs/{LOG}", "Back to production logs", "/production/logs"),
    ("/invoices", "Back to Today", "/today"), (f"/invoices/{INVOICE}", "Back to invoices", "/invoices"),
    (f"/invoices/{INVOICE}/photo", "Back to invoice", f"/invoices/{INVOICE}"), ("/incoming", "Back to inventory", "/inventory"),
    ("/team", "Back to Today", "/today"), ("/team/build", "Back to team", "/team"),
    ("/team/invite", "Back to build team", "/team/build"), ("/team/assign", "Back to build team", "/team/build"),
    ("/team/access", "Back to store", "/store"), ("/team/2", "Back to team", "/team"),
    ("/owner", "Back to Today", "/today"), ("/owner/2", "Back to owner tools", "/owner"),
    ("/owner/cutover", "Back to owner tools", "/owner"), ("/time-tracking", "Back to Today", "/today"),
])
def test_each_real_screen_back_control_has_a_canonical_cold_link_parent(page: Page, full_router_url: str, route: str, label: str, parent: str):
    page.set_default_timeout(5_000)
    page.goto(f"{full_router_url}{route}?role=owner")
    page.get_by_role("button", name=label, exact=True).first.click()
    expect(page).to_have_url(re.compile(rf"{re.escape(parent)}(?:\?.*)?$"))


def test_today_inventory_catalog_forward_chain_and_back_controls(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/today?role=owner")
    page.get_by_role("button", name="Inventory", exact=True).click()
    expect(page).to_have_url(re.compile(r"/inventory(?:\?.*)?$"))
    page.get_by_role("button", name="Open company catalog", exact=True).click()
    expect(page).to_have_url(re.compile(r"/catalog(?:\?.*)?$"))
    page.get_by_role("button", name="Add product", exact=True).click()
    expect(page).to_have_url(re.compile(r"/catalog/new(?:\?.*)?$"))
    page.get_by_role("button", name="Back to catalog", exact=True).click()
    expect(page).to_have_url(re.compile(r"/catalog(?:\?.*)?$"))
    page.get_by_role("button", name="Back to inventory", exact=True).click()
    expect(page).to_have_url(re.compile(r"/inventory(?:\?.*)?$"))


def test_manager_opens_real_heads_up_content_and_returns_to_store(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/store?role=manager")
    page.get_by_role("button", name="Heads Up", exact=True).click()
    expect(page).to_have_url(re.compile(r"/heads-up(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="Heads Up", exact=True)).to_be_visible()
    page.get_by_role("button", name="Back to store", exact=True).click()
    expect(page).to_have_url(re.compile(r"/store(?:\?.*)?$"))


def test_populated_inventory_details_preserve_the_full_forward_and_return_trail(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/inventory?role=owner")
    page.get_by_role("button", name="Open company catalog", exact=True).click()
    page.get_by_role("button", name="View product: Fixture vanilla base", exact=True).click()
    expect(page.get_by_text("VAN-BASE", exact=False).first).to_be_visible()
    page.get_by_role("button", name="Manage packages & barcodes", exact=True).click()
    expect(page.get_by_text("Five kilogram tub", exact=True)).to_be_visible()
    page.get_by_role("button", name="Back to product", exact=True).click()
    page.get_by_role("button", name="Back to catalog", exact=True).click()
    page.get_by_role("button", name="Back to inventory", exact=True).click()
    page.get_by_role("button", name="Open shelves", exact=True).click()
    page.get_by_role("button", name="Open Walk-in freezer", exact=True).click()
    expect(page.get_by_text("Fixture vanilla base", exact=True).first).to_be_visible()
    page.get_by_role("button", name="Back to Open Shelves", exact=True).click()
    page.get_by_role("button", name="Back to inventory", exact=True).click()
    page.get_by_role("button", name="View current inventory", exact=True).click()
    page.get_by_role("button", name=re.compile(r"View stock: Fixture vanilla base")).click()
    expect(page.get_by_text("8.5 kg", exact=False).first).to_be_visible()
    page.get_by_role("button", name="Back to current inventory", exact=True).click()
    page.get_by_role("button", name="Back to inventory", exact=True).click()


def test_owner_team_and_production_review_nested_journeys(page: Page, full_router_url: str):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{full_router_url}/store?role=owner")
    page.get_by_role("button", name="Build team", exact=True).click()
    page.get_by_role("button", name="Invite a new person", exact=True).click()
    expect(page.get_by_role("heading", name="Invite a new person", exact=True)).to_be_visible()
    if target := os.environ.get("NAVIGATION_TEAM_SCREENSHOT"):
        page.screenshot(path=target, full_page=True)
    page.get_by_role("button", name="Back to build team", exact=True).click()
    page.get_by_role("button", name="Back to store", exact=True).click()

    page.goto(f"{full_router_url}/production?role=owner")
    page.get_by_role("button", name="Record today's production", exact=True).click()
    page.get_by_role("checkbox", name="Add Fixture vanilla gelato", exact=True).click()
    page.get_by_role("button", name="Review ingredient use", exact=True).click()
    expect(page.get_by_role("heading", name="Review ingredient use", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Back to production run", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Back to edit batches", exact=True)).to_be_visible()
    if target := os.environ.get("NAVIGATION_PRODUCTION_SCREENSHOT"):
        page.screenshot(path=target, full_page=True)
    page.get_by_role("button", name="Back to edit batches", exact=True).click()
    expect(page.get_by_role("heading", name="Record production", exact=True)).to_be_visible()


@pytest.mark.parametrize("origin,expected", [("/production", "/production"), ("/production/recipes", "/production/recipes")])
def test_new_recipe_modal_cancel_returns_to_its_actual_origin(page: Page, full_router_url: str, origin: str, expected: str):
    page.goto(f"{full_router_url}{origin}?role=owner")
    page.get_by_role("button", name="New recipe", exact=True).click()
    expect(page.locator('div[aria-label="New recipe"]')).to_be_visible()
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page).to_have_url(re.compile(rf"{re.escape(expected)}(?:\?.*)?$"))


def test_submit_only_report_writer_returns_directly_to_today(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/today?role=crew&reports=submit-only")
    page.get_by_role("button", name="Write shift report", exact=True).click()
    expect(page.get_by_role("heading", name="Write a report", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Back to reports", exact=True)).to_have_count(0)
    expect(page.get_by_role("button", name="Shift reports", exact=True)).to_have_count(0)
    page.get_by_role("button", name="Back to Today", exact=True).click()
    expect(page).to_have_url(re.compile(r"/today(?:\?.*)?$"))


def test_owner_nested_origins_and_time_tracking_reload_keep_the_actual_parent(page: Page, full_router_url: str):
    page.set_default_timeout(5_000)
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(f"{full_router_url}/today?role=owner")
    page.get_by_role("button", name="Owner tools", exact=True).click()
    owner_actions = page.get_by_role("heading", name="People & authority", exact=True).locator("..")
    owner_actions.get_by_role("button", name="Time Tracking", exact=True).click()
    expect(page).to_have_url(re.compile(r"/time-tracking\?.*owner"))
    page.reload()
    page.get_by_role("button", name="Back to owner tools", exact=True).click()
    page.get_by_role("button", name="Manage this store's team", exact=True).click()
    page.get_by_role("button", name="Choose a team member", exact=True).click()
    page.get_by_role("button", name="Choose Fixture Manager", exact=True).click()
    page.get_by_role("button", name="Manage Fixture Manager", exact=True).click()
    expect(page).to_have_url(re.compile(r"/team/2(?:\?.*)?$"))
    page.get_by_role("button", name="Back to team", exact=True).click()
    page.get_by_role("button", name="Back to owner tools", exact=True).click()
    page.get_by_role("button", name="Review store sign-in", exact=True).click()
    page.get_by_role("button", name="Back to owner tools", exact=True).click()
    page.get_by_role("button", name="Review Fixture Manager", exact=True).click()
    page.get_by_role("button", name="Back to owner tools", exact=True).click()
    page.get_by_role("button", name="Back to Today", exact=True).click()

    page.goto(f"{full_router_url}/store?role=owner")
    page.get_by_role("button", name="Owner tools", exact=True).click()
    page.get_by_role("button", name="Back to store", exact=True).click()
    expect(page).to_have_url(re.compile(r"/store(?:\?.*)?$"))


def test_receiving_cross_section_return_trails_match_launch_origin(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/today?role=owner")
    page.get_by_role("button", name="Invoices", exact=True).click()
    page.get_by_text("Fixture Dairy", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/invoices/{INVOICE}(?:\?.*)?$"))
    page.get_by_role("button", name="Back to invoices", exact=True).click()
    page.get_by_role("button", name="Back to Today", exact=True).click()

    page.get_by_role("button", name="Inventory", exact=True).click()
    page.get_by_role("button", name="View incoming inventory", exact=True).click()
    page.get_by_role("button", name="Review invoices", exact=True).first.click()
    page.get_by_role("button", name="Back to incoming inventory", exact=True).click()
    page.get_by_role("button", name="Back to inventory", exact=True).click()
    expect(page).to_have_url(re.compile(r"/inventory(?:\?.*)?$"))


def test_stock_count_workspace_returns_through_counts_to_stock(page: Page, full_router_url: str):
    page.goto(f"{full_router_url}/stock?role=owner")
    page.get_by_role("button", name="Count inventory", exact=True).click()
    page.get_by_role("button", name="Resume count", exact=True).click()
    expect(page).to_have_url(re.compile(rf"/counts/{COUNT}(?:\?.*)?$"))
    page.get_by_role("button", name="Back to count inventory", exact=True).click()
    page.get_by_role("button", name="Back to current inventory", exact=True).click()
    expect(page).to_have_url(re.compile(r"/stock(?:\?.*)?$"))
