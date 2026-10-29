import json
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import expect


ROOT = Path(__file__).resolve().parents[2]
RECIPE_ID = "11111111-1111-4111-8111-111111111111"
REVISION_ID = "22222222-2222-4222-8222-222222222222"
PRODUCT_ID = "33333333-3333-4333-8333-333333333333"


def browser_contract(page, *, uncertain=False, can_submit=True):
    state = {"posted": None, "attempts": [], "recovery": "unknown", "store": 7, "post_status": 200}
    recipe = {"id": RECIPE_ID, "revisionId": REVISION_ID, "version": 1, "name": "Vanilla bean",
              "yieldAmount": "6", "yieldUnit": "tubs", "instructions": "Fold slowly.",
              "ingredients": [{"productId": PRODUCT_ID, "name": "Cream", "sku": "001", "amount": "2",
                               "unit": "kg", "baseUnit": "kg", "baseAmount": "2"}]}

    def log(log_id):
        return {"id": log_id, "businessDate": "2026-09-29", "state": "confirmed", "createdAt": "2026-09-29T12:00:00Z",
                "createdBy": "Production Person", "entries": [{"name": "Vanilla bean", "batches": 2}],
                "ingredients": [{"productId": PRODUCT_ID, "name": "Cream", "recipeAmount": "4",
                                 "allowanceAmount": "0.04", "quantity": "4.04", "baseUnit": "kg",
                                 "balance": "20", "remaining": "15.96"}]}

    def route(request_route):
        request = request_route.request
        path = urlparse(request.url).path
        if path == "/production.html":
            return request_route.fulfill(status=200, content_type="text/html", body=(ROOT / "production.html").read_text())
        if path == "/production.js":
            return request_route.fulfill(status=200, content_type="application/javascript", body=(ROOT / "production.js").read_text())
        if path == "/production.css":
            return request_route.fulfill(status=200, content_type="text/css", body=(ROOT / "production.css").read_text())
        if path.endswith(".css") or "fonts." in request.url:
            return request_route.fulfill(status=200, content_type="text/css", body="")
        if path == "/api/accounts/status":
            capabilities = ["inventory.view", "production.view"] + (["production.submit"] if can_submit else [])
            return request_route.fulfill(json={"authenticated": True, "actor": {"userId": 9, "storeId": state["store"],
                "role": "production", "capabilities": capabilities},
                "stores": [{"userId": 9, "storeId": state["store"], "storeName": "Test Kitchen", "role": "production", "capabilities": []}]})
        if path == "/api/production/recipes":
            return request_route.fulfill(json={"items": [recipe], "nextCursor": None})
        if path == "/api/production/preview":
            return request_route.fulfill(json={"canConfirm": True, "issues": [], "entries": [{"recipeId": RECIPE_ID,
                "revisionId": REVISION_ID, "name": "Vanilla bean", "yieldAmount": "6", "yieldUnit": "tubs", "batches": 2}], "deductions": [{"productId": PRODUCT_ID,
                "name": "Cream", "recipeAmount": "4", "allowanceAmount": "0.04", "quantity": "4.04",
                "baseUnit": "kg", "balance": "20", "remaining": "15.96"}]})
        if path == "/api/production/logs" and request.method == "POST":
            state["posted"] = json.loads(request.post_data)
            state["attempts"].append(state["posted"])
            if state["post_status"] != 200:
                return request_route.fulfill(status=state["post_status"], json={"error": "Recipe or stock changed."})
            if uncertain and len(state["attempts"]) == 1:
                return request_route.fulfill(status=503, json={"error": "Connection lost."})
            return request_route.fulfill(json=log(state["posted"]["logId"]))
        if path == "/api/production/logs":
            items = [log(state["posted"]["logId"])] if state["posted"] and state["recovery"] == "found" else []
            return request_route.fulfill(json={"items": items, "nextCursor": None})
        if path.startswith("/api/production/logs/"):
            log_id = path.rsplit("/", 1)[-1]
            if state["recovery"] == "found":
                return request_route.fulfill(json=log(log_id))
            if state["recovery"] == "missing":
                return request_route.fulfill(status=404, json={"error": "Not found."})
            return request_route.fulfill(status=503, json={"error": "Recovery unavailable."})
        return request_route.fulfill(status=404, json={"error": "Not found"})

    page.route("**/*", route)
    page.goto("http://127.0.0.1/production.html")
    return state


def select_and_review(page):
    expect(page.get_by_text("Test Kitchen")).to_be_visible()
    page.get_by_role("checkbox", name="Add Vanilla bean").click()
    page.get_by_role("button", name="Add one batch of Vanilla bean").click()
    page.get_by_role("button", name="Review ingredient use").click()
    expect(page.get_by_text("2 batches · makes 6 tubs per batch")).to_be_visible()
    expect(page.get_by_text("1% allowance: +0.04 kg")).to_be_visible()
    expect(page.get_by_text("Total deduction: 4.04 kg")).to_be_visible()
    page.get_by_label("I reviewed every deduction and want to update stock.").check()


def test_rendered_production_confirms_exact_review_with_store_precondition(page):
    state = browser_contract(page)
    select_and_review(page)
    page.get_by_role("button", name="Confirm production and deduct stock").click()
    expect(page.get_by_text("Production saved for 2026-09-29.")).to_be_visible()
    assert state["posted"]["expectedStoreId"] == 7
    assert state["posted"]["entries"] == [{"recipeId": RECIPE_ID, "revisionId": REVISION_ID, "batches": 2}]
    assert state["posted"]["confirmed"] is True


def test_uncertain_submit_404_stays_locked_and_exact_retry_reuses_payload(page):
    state = browser_contract(page, uncertain=True)
    select_and_review(page)
    page.get_by_role("button", name="Confirm production and deduct stock").click()
    expect(page.get_by_text("Recovery is pending", exact=False)).to_be_visible()
    page.get_by_role("button", name="Edit flavors", exact=False).click()
    expect(page.get_by_role("button", name="Clear draft")).to_be_disabled()
    pending_id = state["posted"]["logId"]
    first_payload = state["attempts"][0]
    state["recovery"] = "missing"
    page.reload()
    expect(page.get_by_text("original request may still finish", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Clear draft")).to_be_disabled()
    page.get_by_role("button", name="Retry saved submission").click()
    expect(page.get_by_text(f"Stock deductions are recorded in log {pending_id}.", exact=False)).to_be_visible()
    assert state["attempts"] == [first_payload, first_payload]


def test_store_change_between_review_and_confirm_never_posts(page):
    state = browser_contract(page)
    select_and_review(page)
    state["store"] = 8
    page.get_by_role("button", name="Confirm production and deduct stock").click()
    page.wait_for_timeout(100)
    assert state["posted"] is None


def test_view_only_account_sees_recipes_without_submission_controls(page):
    browser_contract(page, can_submit=False)
    # This flavor also exists in the hidden Today panel; inspect the recipe book.
    book = page.locator("#recipes-view")
    expect(book).to_be_visible()
    expect(book.get_by_role("heading", name="Vanilla bean", exact=True)).to_be_visible()
    recipe = book.get_by_role("button", name="Vanilla bean Makes 6 tubs per batch", exact=True)
    recipe.click()
    expect(recipe).to_have_attribute("aria-expanded", "true")
    expect(book.get_by_text("2 kg Cream", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Today", exact=True)).to_be_hidden()
    expect(page.get_by_role("checkbox", name="Add Vanilla bean")).to_be_hidden()
    expect(page.get_by_role("button", name="Review ingredient use")).to_be_hidden()
    expect(page.get_by_role("button", name="Confirm production and deduct stock")).to_be_hidden()


def test_definitive_conflict_unlocks_same_draft_for_correction(page):
    state = browser_contract(page)
    select_and_review(page)
    original = page.evaluate("JSON.parse(sessionStorage.getItem('shiftly.production.draft.v2')).draft")
    state["post_status"] = 409
    page.get_by_role("button", name="Confirm production and deduct stock").click()
    expect(page.get_by_text("Nothing was recorded", exact=False)).to_be_visible()
    expect(page.get_by_role("button", name="Clear draft")).to_be_enabled()
    expect(page.get_by_text("1 flavor selected.")).to_be_visible()
    expect(page.get_by_role("button", name="Retry saved submission")).to_be_hidden()
    current = page.evaluate("JSON.parse(sessionStorage.getItem('shiftly.production.draft.v2')).draft")
    assert current == original
