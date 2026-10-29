import hashlib
from concurrent.futures import ThreadPoolExecutor

from playwright.sync_api import expect

import reporting
from database import db_connection


def login(page, workspace, role):
    page.goto(f"{workspace['base_url']}/")
    page.locator("#username").fill(workspace["manager_username" if role == "manager" else "crew_username"])
    password = workspace["manager_password"] if role == "manager" else workspace["crew_password"]
    page.locator("#password").fill(password)
    page.locator("#sign-in-form button[type='submit']").click()
    page.wait_for_url(f"**/{'manager' if role == 'manager' else 'crew'}.html")


def logout(page):
    page.locator("details summary").click()
    page.locator("button", has_text="Log Out").click()
    page.wait_for_url("**/")


def test_crew_login_submission_and_logout_on_mobile(page, browser_workspace):
    page.set_viewport_size({"width": 390, "height": 844})
    login(page, browser_workspace, "crew")

    assert page.evaluate("window.innerWidth") == 390
    page.locator("#employee").fill("Jordan")
    page.locator("#shift").select_option("closing")
    page.locator("#notes").fill("The team completed the close and logged the delivery.")
    page.locator("#generate-button").click()
    expect(page.locator("#result-content")).to_be_visible()
    expect(page.locator("#result-summary")).to_contain_text("Jordan")

    logout(page)
    expect(page.locator("#sign-in-form")).to_be_visible()


def test_manager_review_heads_up_and_safe_text(page, browser_workspace, seed_report, complete_jobs):
    untrusted_name = '<img src=x onerror="window.__injected = true">'
    seed_report(browser_workspace["store_id"], untrusted_name, "<b>literal notes</b>")
    complete_jobs()
    login(page, browser_workspace, "manager")

    row = page.locator(".report-row").first
    expect(row).to_contain_text(untrusted_name)
    assert row.locator("img").count() == 0
    row.click()
    expect(page.locator("#manager-result-title")).to_contain_text(untrusted_name)
    assert page.locator("#manager-result-title img").count() == 0

    page.locator("#heads-up-update").click()
    page.locator("#heads-up-input").fill("<strong>Close checklist</strong>")
    page.locator("#heads-up-save").click()
    expect(page.locator("#manager-heads-up")).to_have_text("<strong>Close checklist</strong>")

    logout(page)
    login(page, browser_workspace, "crew")
    expect(page.locator("#heads-up-message")).to_have_text("<strong>Close checklist</strong>")
    logout(page)


def test_manager_weekly_pending_to_ready_discloses_partial_coverage(
    page, browser_workspace, seed_report
):
    for index in range(55):
        seed_report(
            browser_workspace["store_id"],
            f"Crew {index}",
            f"Report {index} includes a concrete shift detail.",
            age_seconds=index + 1,
        )

    with db_connection() as holder:
        holder.autocommit = True
        lock_key = f"shiftly:weekly:{browser_workspace['store_id']}"
        holder.execute("SELECT pg_advisory_lock(hashtextextended(%s, 0))", (lock_key,))
        try:
            login(page, browser_workspace, "manager")
            expect(page.locator("#weekly-overview")).to_contain_text(
                "Preparing the weekly overview", timeout=5_000
            )
        finally:
            holder.execute("SELECT pg_advisory_unlock(hashtextextended(%s, 0))", (lock_key,))

    expect(page.locator("#weekly-overview")).to_contain_text(
        "Partial overview: includes 50 of 55 reports", timeout=15_000
    )
    logout(page)
