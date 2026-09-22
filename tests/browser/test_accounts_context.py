"""Browser acceptance for private state when another tab changes the session."""
from playwright.sync_api import expect

from database import db_connection


def _named_login(page, workspace, role):
    with db_connection() as connection:
        username = connection.execute(
            "SELECT username FROM account_users WHERE id=%s", (workspace["users"][role],),
        ).fetchone()[0]
    page.goto(workspace["base_url"] + "/")
    page.locator("#store-code").fill(workspace["stores"][0]["code"])
    page.locator("#username").fill(username)
    page.locator("#password").fill(workspace["password"])
    page.locator("#sign-in-form button[type=submit]").click()
    page.wait_for_url("**/manager.html")


def _refocus(page):
    page.bring_to_front()
    # Headless Chromium can keep both documents focused. Deliver the same
    # standard lifecycle event explicitly after the real tab change so these
    # checks exercise refresh/clearing rather than desktop focus emulation.
    page.evaluate("window.dispatchEvent(new Event('focus'))")


def test_store_switch_in_another_tab_clears_old_store_draft(page, named_workspace):
    workspace = named_workspace
    first_store, second_store = workspace["stores"][:2]
    _named_login(page, workspace, "owner")
    page.goto(workspace["base_url"] + "/crew.html")
    expect(page.locator("#crew-store-name")).to_have_text(first_store["name"])
    page.locator("#employee").fill("Previous store unfinished author")
    page.locator("#notes").fill("Private unfinished draft belonging only to the first store.")

    other_tab = page.context.new_page()
    try:
        other_tab.goto(workspace["base_url"] + "/accounts.html")
        other_tab.locator("#store-select").select_option(str(second_store["id"]))
        with other_tab.expect_response(lambda response: response.url.endswith("/api/accounts/switch-store")
                                       and response.request.method == "POST") as switched:
            other_tab.locator("#switch-store").click()
        assert switched.value.status == 200
        assert switched.value.json()["actor"]["storeId"] == second_store["id"]
        expect(other_tab.locator("body")).to_contain_text(second_store["name"])
        _refocus(page)
        expect(page.locator("#notes")).to_have_value("")
        expect(page.locator("#employee")).not_to_have_value("Previous store unfinished author")
        expect(page.locator("#crew-store-name")).to_have_text(second_store["name"])
        assert page.request.get(workspace["base_url"] + "/api/accounts/status").json()["actor"]["storeId"] == second_store["id"]
        with db_connection() as connection:
            assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 0
    finally:
        other_tab.close()


def test_logout_all_in_another_tab_removes_private_report_and_back_history(
    page, named_workspace, seed_report, complete_jobs,
):
    workspace = named_workspace
    private_notes = "Private manager-only report before the other tab signs every session out."
    seed_report(workspace["stores"][0]["id"], "Context Crew", private_notes)
    complete_jobs()
    _named_login(page, workspace, "manager")
    expect(page.locator("#manager-result-summary")).to_have_text(private_notes)
    # Keep an earlier private page in the real history, so Back exercises more
    # than the current page being replaced by the sign-in redirect.
    page.goto(workspace["base_url"] + "/accounts.html")
    expect(page.locator("#account-profile")).to_contain_text(workspace["stores"][0]["name"])
    page.goto(workspace["base_url"] + "/manager.html")
    expect(page.locator("#manager-result-summary")).to_have_text(private_notes)

    other_tab = page.context.new_page()
    try:
        other_tab.goto(workspace["base_url"] + "/accounts.html")
        other_tab.once("dialog", lambda dialog: dialog.accept())
        other_tab.locator("#logout-all").click()
        other_tab.wait_for_url("**/")
        _refocus(page)
        page.wait_for_url("**/")
        expect(page.locator("body")).not_to_contain_text(private_notes)
        for _ in range(2):
            page.go_back()
            expect(page.locator("body")).not_to_contain_text(private_notes)
        assert page.request.get(workspace["base_url"] + "/api/accounts/status").json()["authenticated"] is False
    finally:
        other_tab.close()


def test_logout_all_in_another_session_clears_private_roster_and_invitation(page, named_workspace):
    workspace = named_workspace
    _named_login(page, workspace, "owner")
    page.goto(workspace["base_url"] + "/accounts.html")
    expect(page.locator("#team-list")).to_contain_text("Account Crew")
    page.locator("#invite-username").fill("private-context-invite")
    page.locator("#invite-display-name").fill("Private Context Invitee")
    page.locator("#invite-role").select_option("crew")
    page.locator("#invite-form button[type=submit]").click()
    expect(page.locator("#invitation-code")).not_to_have_value("")
    secret = page.locator("#invitation-code").input_value()

    # Use another cookie jar here: the original page keeps its now-revoked
    # named token and must clear private data on a 401, not merely on a clean
    # unauthenticated status after a shared cookie was removed.
    other_context = page.context.browser.new_context()
    other_tab = other_context.new_page()
    try:
        _named_login(other_tab, workspace, "owner")
        other_tab.goto(workspace["base_url"] + "/accounts.html")
        other_tab.once("dialog", lambda dialog: dialog.accept())
        other_tab.locator("#logout-all").click()
        other_tab.wait_for_url("**/")
        _refocus(page)
        page.wait_for_url("**/")
        expect(page.locator("body")).not_to_contain_text("Private Context Invitee")
        expect(page.locator("body")).not_to_contain_text("Account Crew")
        assert page.locator("#invitation-code").count() == 0
        assert secret not in page.evaluate("[...document.querySelectorAll('input,textarea')].map(element => element.value).join(' ')")
    finally:
        other_context.close()
