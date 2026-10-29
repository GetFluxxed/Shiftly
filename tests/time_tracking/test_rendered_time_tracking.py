"""Rendered owner-only, device-local time tracking journeys through the real Expo router."""
import os
import re
from pathlib import Path

from playwright.sync_api import Page, expect

from tests.inventory_services.test_rendered_router import router_bundle, router_url  # noqa: F401


def open_tracking(page: Page, router_url: str):
    page.goto(f"{router_url}/time-tracking?role=owner")
    expect(page.get_by_role("heading", name="Time Tracking", exact=True)).to_be_visible()


def add_member(page: Page, name: str):
    page.get_by_role("button", name="Add member", exact=True).click()
    expect(page.get_by_role("heading", name="Add crew member", exact=True)).to_be_visible()
    page.get_by_label("Name", exact=True).fill(name)
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_text(name, exact=True)).to_be_visible()


def edit_member(page: Page, name: str):
    page.get_by_role("button", name=f"Edit {name}", exact=True).click()
    expect(page.get_by_role("heading", name="Crew member", exact=True)).to_be_visible()


def timer_button(page: Page, member: str, hours: int):
    spoken = "3 hours 30 minutes" if hours == 3 else "5 hours 30 minutes"
    return page.get_by_role("button", name=re.compile(rf"^{re.escape(member)}, {spoken} timer,"))


def test_today_shortcut_is_nested_under_owner_tools_and_role_guarded(page: Page, router_url: str):
    page.goto(f"{router_url}/today?role=owner")
    owner = page.get_by_role("button", name="Owner tools", exact=True)
    shortcut = page.get_by_role("button", name="Time Tracking", exact=True)
    expect(owner).to_be_visible()
    expect(shortcut).to_be_visible()
    assert shortcut.bounding_box()["y"] > owner.bounding_box()["y"]
    shortcut.click()
    expect(page).to_have_url(re.compile(r".*/time-tracking(?:\?.*)?$"))
    expect(page.get_by_role("heading", name="Time Tracking", exact=True)).to_be_visible()

    page.goto(f"{router_url}/today?role=crew")
    expect(page.get_by_role("button", name="Time Tracking", exact=True)).to_have_count(0)
    page.goto(f"{router_url}/time-tracking?role=crew")
    expect(page).to_have_url(re.compile(r".*/today(?:\?.*)?$"))
    expect(page.get_by_role("button", name="Time Tracking", exact=True)).to_have_count(0)


def test_member_add_duplicate_rename_and_remove_confirmation(page: Page, router_url: str):
    open_tracking(page, router_url)
    add_member(page, "Avery Stone")
    add_member(page, "Jordan Lee")

    page.get_by_role("button", name="Add member", exact=True).click()
    page.get_by_label("Name", exact=True).fill("Avery Stone")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("heading", name="Add crew member", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"already exists")).last).to_be_visible()
    page.get_by_role("button", name="Cancel", exact=True).click()

    edit_member(page, "Jordan Lee")
    name = page.get_by_label("Name", exact=True)
    name.fill("Jordan Rivera")
    expect(name).to_have_value("Jordan Rivera")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_text("Jordan Rivera", exact=True)).to_be_visible()
    expect(page.get_by_text("Jordan Lee", exact=True)).to_have_count(0)

    edit_member(page, "Jordan Rivera")
    page.get_by_role("button", name="Remove member", exact=True).click()
    expect(page.get_by_role("heading", name="Remove crew member?", exact=True)).to_be_visible()
    page.get_by_role("button", name="Keep member", exact=True).click()
    expect(page.get_by_role("heading", name="Crew member", exact=True)).to_be_visible()
    page.get_by_role("button", name="Remove member", exact=True).click()
    page.get_by_role("button", name="Remove Jordan Rivera", exact=True).click()
    expect(page.get_by_text("Jordan Rivera", exact=True)).to_have_count(0)
    expect(page.get_by_text("Avery Stone", exact=True)).to_be_visible()


def test_independent_timers_expire_without_negative_values_and_new_shift_resets(page: Page, router_url: str):
    page.clock.install(time=2_000_000_000_000)
    open_tracking(page, router_url)
    add_member(page, "Avery")
    page.get_by_role("button", name="Clock in Avery", exact=True).click()
    short = timer_button(page, "Avery", 3)
    long = timer_button(page, "Avery", 5)
    expect(short).to_have_attribute("aria-label", re.compile(r"ready$"))
    short.click()
    page.clock.fast_forward(60 * 60 * 1000)
    long.click()
    page.clock.fast_forward(int(2.5 * 60 * 60 * 1000))

    expect(short).to_have_attribute("aria-label", re.compile(r"complete$"))
    expect(short.get_by_text("0:00:00", exact=True)).to_be_visible()
    expect(long.get_by_text(re.compile(r"^2:59:5[0-9]$"))).to_be_visible()
    assert "-" not in short.inner_text()
    assert "-" not in long.inner_text()

    page.get_by_role("button", name="Clock out Avery", exact=True).click()
    edit_member(page, "Avery")
    expect(page.get_by_text("RECENT SHIFTS · UP TO 10 SAVED", exact=True)).to_be_visible()
    expect(page.get_by_text(re.compile(r"^3:30:0[0-9]$")).last).to_be_visible()
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Clock in Avery", exact=True).click()
    expect(timer_button(page, "Avery", 3)).to_have_attribute("aria-label", re.compile(r"ready$"))
    expect(timer_button(page, "Avery", 3).get_by_text("3:30:00", exact=True)).to_be_visible()
    expect(timer_button(page, "Avery", 5).get_by_text("5:30:00", exact=True)).to_be_visible()


def test_reload_keeps_member_shift_and_independent_timer_timestamps(page: Page, router_url: str):
    page.clock.install(time=2_000_000_000_000)
    open_tracking(page, router_url)
    add_member(page, "Persistent Avery")
    page.get_by_role("button", name="Clock in Persistent Avery", exact=True).click()
    timer_button(page, "Persistent Avery", 3).click()
    page.clock.fast_forward(30 * 60 * 1000)
    timer_button(page, "Persistent Avery", 5).click()
    page.clock.fast_forward(30 * 60 * 1000)
    expect(timer_button(page, "Persistent Avery", 3).get_by_text(re.compile(r"^2:29:5[0-9]$"))).to_be_visible()
    expect(timer_button(page, "Persistent Avery", 5).get_by_text(re.compile(r"^4:59:5[0-9]$"))).to_be_visible()

    page.reload()
    expect(page.get_by_text("Persistent Avery", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name="Clock out Persistent Avery", exact=True)).to_be_visible()
    expect(timer_button(page, "Persistent Avery", 3).get_by_text(re.compile(r"^2:29:5[0-9]$"))).to_be_visible()
    expect(timer_button(page, "Persistent Avery", 5).get_by_text(re.compile(r"^4:59:5[0-9]$"))).to_be_visible()


def test_viewports_have_no_horizontal_overflow_and_optional_screenshots(page: Page, router_url: str):
    screenshot_dir = os.environ.get("TIME_TRACKING_SCREENSHOT_DIR")
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    for width in (320, 390, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        open_tracking(page, router_url)
        if page.get_by_text("Viewport Avery", exact=True).count() == 0:
            add_member(page, "Viewport Avery")
            page.get_by_role("button", name="Clock in Viewport Avery", exact=True).click()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        expect(page.get_by_role("heading", name="Time Tracking", exact=True)).to_be_visible()
        expect(page.get_by_role("button", name=re.compile(r"^Viewport Avery, 3 hours 30 minutes timer,"))).to_be_visible()
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / f"time-tracking-{width}.png"), full_page=True)


def test_storage_failure_preserves_single_change_surfaces_error_and_does_not_retry(page: Page, router_url: str):
    open_tracking(page, router_url)
    page.wait_for_timeout(500)
    page.evaluate("""
      window.__timeTrackingWrites = 0;
      window.__originalStorageSetItem = Storage.prototype.setItem;
      Storage.prototype.setItem = function () {
        window.__timeTrackingWrites += 1;
        throw new Error('injected storage failure');
      };
      void 0;
    """)
    add_member(page, "Unsaved Avery")
    expect(page.get_by_text("Unsaved Avery", exact=True)).to_have_count(1)
    expect(page.get_by_text(re.compile(r"could not save on this device"))).to_be_visible()
    assert page.evaluate("window.__timeTrackingWrites") == 1
    page.wait_for_timeout(500)
    assert page.evaluate("window.__timeTrackingWrites") == 1
