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


def break_button(page: Page, member: str, minutes: int):
    return page.get_by_role("button", name=re.compile(rf"^{re.escape(member)}, {minutes} minute break,"))


def member_details_button(page: Page, name: str):
    return page.get_by_role("button", name=f"View {name} timers and shift details", exact=True)


def open_member_details(page: Page, name: str):
    member_details_button(page, name).click()
    expect(page.get_by_role("heading", name=name, exact=True)).to_be_visible()
    expect(page.get_by_role("dialog")).to_have_count(1)


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


def test_large_roster_compacts_and_member_management_returns_to_details(page: Page, router_url: str):
    open_tracking(page, router_url)
    for name in ("Avery", "Jordan", "Morgan"):
        add_member(page, name)
    expect(timer_button(page, "Avery", 3)).to_be_visible()
    add_member(page, "Casey")
    expect(timer_button(page, "Avery", 3)).to_have_count(0)
    expect(page.get_by_role("button", name=re.compile(r"^View .* timers and shift details$"))).to_have_count(4)

    page.evaluate("""() => {
        window.__detailInputFocuses = 0;
        document.addEventListener('focusin', event => {
            if (event.target.tagName === 'INPUT') window.__detailInputFocuses += 1;
        });
    }""")
    open_member_details(page, "Avery")
    assert page.evaluate("document.activeElement.tagName") != "INPUT"
    assert page.evaluate("window.__detailInputFocuses") == 0
    expect(timer_button(page, "Avery", 3)).to_be_disabled()
    page.get_by_role("dialog").get_by_role("button", name="Clock in Avery", exact=True).click()
    expect(timer_button(page, "Avery", 3)).to_be_enabled()
    page.get_by_role("button", name="Edit member", exact=True).click()
    page.get_by_label("Name", exact=True).fill("Discarded draft")
    page.get_by_role("button", name="Cancel", exact=True).click()
    page.get_by_role("button", name="Edit member", exact=True).click()
    expect(page.get_by_label("Name", exact=True)).to_have_value("Avery")
    page.get_by_label("Name", exact=True).fill("Jordan")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("dialog").get_by_text(re.compile(r"already exists"))).to_be_visible()
    page.get_by_label("Name", exact=True).fill("Avery Stone")
    page.get_by_role("button", name="Save", exact=True).click()
    expect(page.get_by_role("heading", name="Avery Stone", exact=True)).to_be_visible()
    expect(page.get_by_role("dialog")).to_have_count(1)
    page.get_by_role("button", name="Close", exact=True).click()
    expect(member_details_button(page, "Avery Stone")).to_be_visible()

    open_member_details(page, "Casey")
    page.get_by_role("button", name="Edit member", exact=True).click()
    page.get_by_role("button", name="Remove member", exact=True).click()
    page.get_by_role("button", name="Keep member", exact=True).click()
    page.get_by_role("button", name="Remove member", exact=True).click()
    page.get_by_role("button", name="Remove Casey", exact=True).click()
    expect(page.get_by_role("dialog")).to_have_count(0)
    expect(member_details_button(page, "Avery Stone")).to_be_visible()
    expect(timer_button(page, "Avery Stone", 3)).to_be_visible()
    expect(page.get_by_role("button", name="Clock out Avery Stone", exact=True)).to_be_visible()


def test_compact_timers_keep_running_and_reset_within_one_modal(page: Page, router_url: str):
    page.clock.install(time=2_000_000_000_000)
    open_tracking(page, router_url)
    for name in ("Avery", "Jordan", "Morgan", "Casey"):
        add_member(page, name)
    page.get_by_role("button", name="Clock in Avery", exact=True).click()
    open_member_details(page, "Avery")
    timer_button(page, "Avery", 3).click()
    page.clock.fast_forward(60 * 60 * 1000)
    timer_button(page, "Avery", 5).click()
    page.get_by_role("button", name="Close", exact=True).click()
    page.clock.fast_forward(int(2.5 * 60 * 60 * 1000))
    expect(member_details_button(page, "Avery")).to_contain_text("Complete")
    page.reload()
    expect(member_details_button(page, "Avery")).to_contain_text("Complete")

    open_member_details(page, "Avery")
    expect(timer_button(page, "Avery", 3)).to_have_attribute("aria-label", re.compile(r"complete$"))
    expect(timer_button(page, "Avery", 5)).to_have_attribute("aria-label", re.compile(r"2:59:5[0-9] remaining$"))
    timer_button(page, "Avery", 5).click()
    expect(page.get_by_role("dialog")).to_have_count(1)
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(page.get_by_role("heading", name="Avery", exact=True)).to_be_visible()
    expect(timer_button(page, "Avery", 5)).to_have_attribute("aria-label", re.compile(r"remaining$"))
    timer_button(page, "Avery", 3).click()
    expect(page.get_by_role("dialog")).to_have_count(1)
    page.get_by_role("button", name="Reset timer", exact=True).click()
    expect(page.get_by_role("heading", name="Avery", exact=True)).to_be_visible()
    expect(timer_button(page, "Avery", 3)).to_have_attribute("aria-label", re.compile(r"ready$"))
    expect(timer_button(page, "Avery", 5)).to_have_attribute("aria-label", re.compile(r"remaining$"))
    page.get_by_role("dialog").get_by_role("button", name="Clock out Avery", exact=True).click()
    expect(timer_button(page, "Avery", 3)).to_be_disabled()
    expect(page.get_by_text("RECENT SHIFTS · UP TO 10 SAVED", exact=True)).to_be_visible()
    page.get_by_role("button", name="Close", exact=True).click()
    expect(page.get_by_role("button", name="Clock in Avery", exact=True)).to_be_visible()


def test_compact_roster_and_member_sheet_fit_phone_and_tablet(page: Page, router_url: str):
    screenshot_dir = os.environ.get("TIME_TRACKING_SCREENSHOT_DIR")
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    long_name = "Alexandria Montgomery-Wellington"
    page.set_viewport_size({"width": 390, "height": 900})
    open_tracking(page, router_url)
    for name in (long_name, "Jordan Lee", "Morgan Chen", "Casey Rivera", "Sam Patel", "Taylor Brooks"):
        add_member(page, name)
    page.get_by_role("button", name=f"Clock in {long_name}", exact=True).click()
    for width in (320, 390, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        member_details_button(page, long_name).scroll_into_view_if_needed()
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        row = member_details_button(page, long_name).bounding_box()
        clock = page.get_by_role("button", name=f"Clock out {long_name}", exact=True).bounding_box()
        assert row["height"] >= 44
        assert clock["height"] >= 44
        assert clock["x"] >= 0 and clock["x"] + clock["width"] <= width
        if width == 390:
            assert row["height"] < 170, "Compact rows should be much shorter than expanded timer cards"
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / f"time-tracking-compact-{width}.png"), full_page=True)
        open_member_details(page, long_name)
        expect(timer_button(page, long_name, 3)).to_be_visible()
        expect(timer_button(page, long_name, 5)).to_be_visible()
        for timer in (timer_button(page, long_name, 3), timer_button(page, long_name, 5)):
            box = timer.bounding_box()
            assert box["x"] >= 0 and box["x"] + box["width"] <= width
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / f"time-tracking-member-sheet-{width}.png"), full_page=True)
        page.get_by_role("button", name="Close", exact=True).click()


def test_break_timers_are_modal_only_independent_and_survive_reload(page: Page, router_url: str):
    page.clock.install(time=2_000_000_000_000)
    page.set_viewport_size({"width": 390, "height": 900})
    open_tracking(page, router_url)
    add_member(page, "Avery")
    add_member(page, "Jordan")
    expect(break_button(page, "Avery", 10)).to_have_count(0)
    open_member_details(page, "Avery")
    dialog = page.get_by_role("dialog")
    expect(break_button(page, "Avery", 10)).to_be_disabled()
    expect(break_button(page, "Avery", 30)).to_be_disabled()
    dialog.get_by_role("button", name="Clock in Avery", exact=True).click()
    # Expanded cards remain behind the modal, so scope work timer actions to it.
    dialog.get_by_role("button", name=re.compile(r"^Avery, 3 hours 30 minutes timer,")).click()
    dialog.get_by_role("button", name=re.compile(r"^Avery, 5 hours 30 minutes timer,")).click()
    break_button(page, "Avery", 10).click()
    page.clock.fast_forward(2 * 60_000)
    break_button(page, "Avery", 30).click()
    page.get_by_role("button", name="Close", exact=True).click()
    page.clock.fast_forward(8 * 60_000)
    page.reload()
    open_member_details(page, "Avery")
    expect(break_button(page, "Avery", 10)).to_have_attribute("aria-label", re.compile(r"complete$"))
    expect(break_button(page, "Avery", 30)).to_have_attribute("aria-label", re.compile(r"21:5[0-9] remaining$"))
    short = dialog.get_by_role("button", name=re.compile(r"^Avery, 3 hours 30 minutes timer,"))
    long = dialog.get_by_role("button", name=re.compile(r"^Avery, 5 hours 30 minutes timer,"))
    expect(short).to_have_attribute("aria-label", re.compile(r"3:19:5[0-9] remaining$"))
    expect(long).to_have_attribute("aria-label", re.compile(r"5:19:5[0-9] remaining$"))

    break_button(page, "Avery", 10).click()
    expect(page.get_by_role("heading", name="10 minute break", exact=True)).to_be_visible()
    expect(dialog).to_have_count(1)
    page.get_by_role("button", name="Cancel", exact=True).click()
    expect(break_button(page, "Avery", 10)).to_have_attribute("aria-label", re.compile(r"complete$"))
    break_button(page, "Avery", 10).click()
    page.get_by_role("button", name="Reset break", exact=True).click()
    expect(page.get_by_role("heading", name="Avery", exact=True)).to_be_visible()
    expect(break_button(page, "Avery", 10)).to_have_attribute("aria-label", re.compile(r"ready$"))
    expect(break_button(page, "Avery", 30)).to_have_attribute("aria-label", re.compile(r"remaining$"))
    expect(short).to_have_attribute("aria-label", re.compile(r"3:19:5[0-9] remaining$"))
    # Resetting a work timer also leaves the active break untouched.
    short.click()
    page.get_by_role("button", name="Reset", exact=True).click()
    expect(break_button(page, "Avery", 30)).to_have_attribute("aria-label", re.compile(r"remaining$"))
    page.get_by_role("button", name="Close", exact=True).click()

    open_member_details(page, "Jordan")
    expect(break_button(page, "Jordan", 10)).to_have_attribute("aria-label", re.compile(r"disabled$"))
    dialog.get_by_role("button", name="Clock in Jordan", exact=True).click()
    expect(break_button(page, "Jordan", 10)).to_have_attribute("aria-label", re.compile(r"ready$"))
    expect(break_button(page, "Jordan", 30)).to_have_attribute("aria-label", re.compile(r"ready$"))
    page.get_by_role("button", name="Close", exact=True).click()

    open_member_details(page, "Avery")
    dialog.get_by_role("button", name="Clock out Avery", exact=True).click()
    expect(break_button(page, "Avery", 30)).to_be_disabled()
    dialog.get_by_role("button", name="Clock in Avery", exact=True).click()
    expect(break_button(page, "Avery", 10)).to_have_attribute("aria-label", re.compile(r"ready$"))
    expect(break_button(page, "Avery", 30)).to_have_attribute("aria-label", re.compile(r"ready$"))


def test_break_section_fits_small_phones_and_tablets(page: Page, router_url: str):
    screenshot_dir = os.environ.get("TIME_TRACKING_SCREENSHOT_DIR")
    if screenshot_dir:
        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
    open_tracking(page, router_url)
    for name in ("Avery Stone", "Jordan Lee", "Morgan Chen", "Casey Rivera"):
        add_member(page, name)
    page.get_by_role("button", name="Clock in Avery Stone", exact=True).click()
    for width in (320, 390, 1024):
        page.set_viewport_size({"width": width, "height": 900})
        open_member_details(page, "Avery Stone")
        for minutes in (10, 30):
            button = break_button(page, "Avery Stone", minutes)
            button.scroll_into_view_if_needed()
            box = button.bounding_box()
            assert box["height"] >= 44
            assert box["x"] >= 0 and box["x"] + box["width"] <= width
        assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
        if screenshot_dir:
            page.screenshot(path=str(Path(screenshot_dir) / f"time-tracking-breaks-{width}.png"), full_page=True)
        page.get_by_role("button", name="Close", exact=True).click()
