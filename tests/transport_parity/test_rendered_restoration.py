"""Rendered regression coverage for encrypted workspace restoration."""
import json

from playwright.sync_api import expect

from tests.transport_parity.test_rendered_accounts import accounts_bundle, native_accounts
from tests.transport_parity.test_mobile_api import mobile


def open_reports(page):
    page.get_by_role('navigation').get_by_role('button', name='Reports', exact=True).click()
    write = page.get_by_role('button', name='Write a report', exact=True)
    if write.count():
        write.click()
    expect(page.get_by_label('Shift notes', exact=True)).to_be_visible()


def lock_and_retry(page):
    page.evaluate('window.__accountsTest.lock()')
    expect(page.get_by_text('Workspace locked', exact=False)).to_be_visible()
    page.evaluate('window.__accountsTest.retry()')
    expect(page.get_by_role('navigation', name='Main navigation')).to_be_visible()


def test_report_draft_survives_lock_reopen_and_explicit_discard(page, native_accounts):
    base, _ = native_accounts
    page.goto(base + '/accounts?as=crew')
    open_reports(page)
    notes = page.get_by_label('Shift notes', exact=True)
    notes.fill('Walk-in temperature needs another check at 6 PM.')

    lock_and_retry(page)
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value(
        'Walk-in temperature needs another check at 6 PM.'
    )

    page.evaluate('window.__workspaceTest.flush()')
    page.goto(base + '/today?as=crew')
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value(
        'Walk-in temperature needs another check at 6 PM.'
    )

    page.get_by_role('button', name='Discard draft', exact=True).click()
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value('')
    page.evaluate('window.__workspaceTest.flush()')
    lock_and_retry(page)
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value('')


def test_report_lost_response_requires_acknowledgement_before_another_send(page, native_accounts):
    base, _ = native_accounts
    page.goto(base + '/accounts?as=crew')
    open_reports(page)
    notes = page.get_by_label('Shift notes', exact=True)
    notes.fill('Deposit is sealed; verify the safe log before resending.')

    def lose_response(route):
        if route.request.method == 'POST':
            route.fetch()
            route.abort()
        else:
            route.continue_()

    page.route('**/api/mobile/reports', lose_response)
    page.get_by_role('button', name='Send shift report', exact=True).click()
    expect(page.get_by_text(
        'Submission could not be confirmed. Check the inbox or with your manager before sending again.',
        exact=True,
    )).to_be_visible()
    expect(page.get_by_role('button', name='Send shift report', exact=True)).to_be_disabled()

    lock_and_retry(page)
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value(
        'Deposit is sealed; verify the safe log before resending.'
    )
    expect(page.get_by_role('button', name='Send shift report', exact=True)).to_be_disabled()
    page.get_by_role('button', name='I checked — keep editing', exact=True).click()
    expect(page.get_by_role('button', name='Send shift report', exact=True)).to_be_enabled()


def test_report_checkpoint_context_drift_never_starts_post(page, native_accounts):
    base, m = native_accounts
    report_posts = []
    page.on('request', lambda request: report_posts.append(request.url)
            if request.method == 'POST' and request.url.endswith('/api/mobile/reports') else None)
    page.goto(base + '/accounts?as=owner')
    open_reports(page)
    page.get_by_label('Shift notes', exact=True).fill('This draft belongs only to the first store.')
    page.evaluate("""() => {
      const originalFlush = window.__workspaceTest.flush.bind(window.__workspaceTest);
      let release;
      const gate = new Promise(resolve => { release = resolve; });
      window.__checkpointRelease = release;
      window.__workspaceTest.flush = async () => {
        await gate;
        return originalFlush();
      };
    }""")

    page.get_by_role('button', name='Send shift report', exact=True).click()
    page.evaluate('(storeId) => window.__accountsTest.switchStore(storeId)', m.stores[1])
    page.evaluate('window.__checkpointRelease()')

    expect(page.get_by_role('navigation', name='Main navigation')).to_be_visible()
    assert page.evaluate('window.__accountsTest.getSnapshot().actor.storeId') == m.stores[1]
    assert report_posts == []
    open_reports(page)
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value('')


def test_heads_up_draft_is_discarded_when_server_baseline_changes(page, native_accounts):
    base, m = native_accounts
    token = m.login()
    m.accounts.set_membership(token, user_id=m.users['crew'], role='manager', capabilities=['memberships.manage'])
    m.client.app.state.context.services.stores.save_heads_up(m.stores[0], 'Opening delivery is at eight.')
    page.goto(base + '/heads-up?as=crew')
    page.get_by_role('button', name='Edit Heads Up', exact=True).click()
    page.get_by_label('Message', exact=True).fill('Unsaved local delivery revision')

    page.evaluate('window.__accountsTest.lock()')
    m.client.app.state.context.services.stores.save_heads_up(m.stores[0], 'Opening delivery moved to ten.')
    page.evaluate('window.__accountsTest.retry()')

    expect(page.get_by_text('Opening delivery moved to ten.', exact=True)).to_be_visible()
    expect(page.get_by_label('Message', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Edit Heads Up', exact=True).click()
    expect(page.get_by_label('Message', exact=True)).to_have_value('Opening delivery moved to ten.')


def test_store_switch_drops_report_draft_from_previous_scope(page, native_accounts):
    base, m = native_accounts
    page.goto(base + '/accounts?as=owner')
    open_reports(page)
    page.get_by_label('Shift notes', exact=True).fill('First-store-only handoff')
    page.get_by_role('navigation').get_by_role('button', name='Account', exact=True).click()
    page.get_by_role('button', name='Switch store', exact=True).click()
    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Switch to mobile-second', exact=True).click()
    expect(page.get_by_role('button', name='View permissions', exact=True)).to_be_visible()
    assert page.evaluate('window.__accountsTest.getSnapshot().actor.storeId') == m.stores[1]
    open_reports(page)
    expect(page.get_by_label('Shift notes', exact=True)).to_have_value('')


def test_password_never_enters_workspace_checkpoint(page, native_accounts):
    base, _ = native_accounts
    known_password = 'checkpoint-must-never-store-this-password'
    page.goto(base + '/accounts?as=crew')
    page.get_by_role('button', name='Sign-in & security', exact=True).click()
    page.get_by_role('button', name='Change password', exact=True).click()
    page.get_by_label('Current password', exact=True).fill(known_password)
    page.get_by_label('New password', exact=True).fill(known_password + '-new')
    page.get_by_label('Confirm new password', exact=True).fill(known_password + '-new')
    page.evaluate('window.__workspaceTest.flush()')
    raw = page.evaluate("localStorage.getItem('test.workspace') || ''")
    assert known_password not in raw
    document = json.loads(raw)
    assert all('password' not in key.lower() for key in document['entries'])
