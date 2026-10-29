"""Actual native announcements on phone/tablet against the isolated real API."""
import os
from pathlib import Path

import pytest
from playwright.sync_api import expect

from tests.transport_parity.test_rendered_accounts import accounts_bundle, native_accounts
from tests.transport_parity.test_mobile_api import mobile


def manager(m):
    m.accounts.set_membership(m.login(), user_id=m.users['crew'], role='manager', capabilities=['memberships.manage'])
    return m.login('crew')


def screenshot(page, name):
    if os.environ.get('HEADS_UP_SCREENSHOT_DIR'):
        page.screenshot(path=str(Path(os.environ['HEADS_UP_SCREENSHOT_DIR']) / name), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


@pytest.mark.parametrize('width', [390, 1024])
def test_manager_opens_store_heads_up_creates_edits_and_returns_to_store(page, native_accounts, width):
    base, m = native_accounts
    token = manager(m)
    page.set_viewport_size({'width': width, 'height': 900})
    page.goto(base + '/store?as=crew')
    expect(page.get_by_role('button', name='Store access')).to_have_count(0)
    page.get_by_role('button', name='Heads Up', exact=True).click()
    expect(page.get_by_text('No store updates', exact=True)).to_be_visible()
    page.get_by_role('button', name='Create Heads Up', exact=True).click()
    page.get_by_label('Message', exact=True).fill('Delivery arrives before opening.')
    expect(page.get_by_text('You have an unsaved change.', exact=True)).to_be_visible()
    screenshot(page, f'heads-up-edit-{width}.png')
    page.get_by_role('button', name='Save Heads Up', exact=True).click()
    expect(page.get_by_text('Delivery arrives before opening.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Edit Heads Up', exact=True)).to_be_visible()
    assert m.send('GET', '/api/mobile/heads-up', token=token).json()['message'] == 'Delivery arrives before opening.'
    page.get_by_role('button', name='Edit Heads Up', exact=True).click()
    page.get_by_label('Message', exact=True).fill('An unsaved revision')
    page.get_by_role('button', name='Cancel', exact=True).click()
    expect(page.get_by_text('Delivery arrives before opening.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Edit Heads Up', exact=True).click()
    page.get_by_label('Message', exact=True).fill('Delivery moved to noon.')
    page.get_by_role('button', name='Save Heads Up', exact=True).click()
    expect(page.get_by_text('Delivery moved to noon.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Back to store', exact=True).click()
    expect(page.get_by_role('heading', name='Store', exact=True)).to_be_visible()
    page.get_by_role('navigation').get_by_role('button', name='Today', exact=True).click()
    expect(page.get_by_text('Delivery moved to noon.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Edit Heads Up', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Create Heads Up', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Refresh Heads Up', exact=True).click()
    expect(page.get_by_text('Delivery moved to noon.', exact=True)).to_be_visible()
    today = page.get_by_test_id('workspace-scroll')
    for title in ('Shift reports', 'Inventory', 'Manage team', 'Account'):
        expect(today.get_by_role('button', name=title, exact=True)).to_be_visible()
    screenshot(page, f'today-grid-{width}.png')


def test_crew_sees_announcement_on_today_and_cannot_edit(page, native_accounts):
    base, m = native_accounts
    # Seed only this test's isolated schema through the trusted store service.
    m.client.app.state.context.services.stores.save_heads_up(m.stores[0], 'Check freezer two before opening.')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(base + '/today?as=crew')
    expect(page.get_by_text('Check freezer two before opening.', exact=True)).to_be_visible()
    screenshot(page, 'heads-up-crew-today.png')
    page.get_by_role('button', name='Refresh Heads Up', exact=True).click()
    expect(page.get_by_text('Check freezer two before opening.', exact=True)).to_be_visible()
    page.goto(base + '/heads-up?as=crew')
    expect(page.get_by_text('Check freezer two before opening.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Edit Heads Up', exact=True)).to_have_count(0)
    expect(page.get_by_label('Message', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Back to today', exact=True).click()
    expect(page.get_by_role('button', name='Refresh Heads Up', exact=True)).to_be_visible()


@pytest.mark.parametrize('username', ['owner', 'viewer'])
def test_non_staff_never_fetch_or_display_heads_up_even_on_direct_route(page, native_accounts, username):
    base, _ = native_accounts
    requests = []
    page.on('request', lambda r: requests.append(r.url) if '/api/mobile/heads-up' in r.url else None)
    page.goto(base + '/today?as=' + username)
    expect(page.get_by_test_id('workspace-scroll').get_by_role('button', name='Account', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Heads Up', exact=True)).to_have_count(0)
    page.goto(base + '/heads-up?as=' + username)
    expect(page.get_by_text('Heads Up is unavailable', exact=True)).to_be_visible()
    assert requests == []


def test_manager_failed_save_keeps_draft_after_leaving_until_cancelled(page, native_accounts):
    base, m = native_accounts
    manager(m)
    page.goto(base + '/heads-up?as=crew')
    page.get_by_role('button', name='Create Heads Up', exact=True).click()
    field = page.get_by_label('Message', exact=True)
    field.fill('Keep this draft until I leave.')
    def unavailable(route):
        if route.request.method == 'POST':
            route.fulfill(status=503, content_type='application/json', body='{"error":"Try again later."}')
        else:
            route.continue_()
    page.route('**/api/mobile/heads-up', unavailable)
    page.get_by_role('button', name='Save Heads Up', exact=True).click()
    expect(page.get_by_role('alert')).to_be_visible()
    expect(field).to_have_value('Keep this draft until I leave.')
    page.get_by_role('navigation').get_by_role('button', name='Store', exact=True).click()
    page.get_by_role('button', name='Heads Up', exact=True).click()
    expect(page.get_by_label('Message', exact=True)).to_have_value('Keep this draft until I leave.')
    page.get_by_role('button', name='Cancel', exact=True).click()
    page.get_by_role('button', name='Create Heads Up', exact=True).click()
    expect(page.get_by_label('Message', exact=True)).to_have_value('')
