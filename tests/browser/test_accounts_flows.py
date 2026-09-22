"""Usable named-account workflows through the legacy and FastAPI browsers."""
import re

from playwright.sync_api import expect

from database import db_connection
from tests.browser.conftest import BrowserApi


def login_named(page, workspace, role, *, password=None):
    page.goto(workspace['base_url'] + '/')
    page.locator('#store-code').fill(workspace['stores'][0]['code'])
    page.locator('#username').fill('account-' + role)
    page.locator('#password').fill(password or workspace['password'])
    page.locator('#sign-in-form button[type=submit]').click()
    destination = 'accounts' if role == 'admin' else 'crew' if role in {'crew', 'viewer'} else 'manager'
    page.wait_for_url(f'**/{destination}.html')


def open_account(page, workspace):
    page.goto(workspace['base_url'] + '/accounts.html')
    expect(page.locator('#account-profile')).to_contain_text('Market Street')


def named_cookie(page):
    token = next(cookie['value'] for cookie in page.context.cookies() if cookie['name'] == 'shiftly_account_session')
    return 'shiftly_account_session=' + token


def test_named_crew_reports_with_verified_actor_and_safe_mobile_account(page, named_workspace, tmp_path):
    workspace = named_workspace
    page.set_viewport_size({'width': 390, 'height': 844})
    login_named(page, workspace, 'crew')
    page.locator('#employee').fill('Original typed display name')
    page.locator('#shift').select_option('closing')
    page.locator('#notes').fill('The closing team checked every freezer and restocked the counter.')
    page.locator('#generate-button').click()
    expect(page.locator('#result-content')).to_be_visible()
    with db_connection() as connection:
        assert connection.execute('SELECT actor_user_id,store_id,employee FROM reports').fetchone() == (
            workspace['users']['crew'], workspace['stores'][0]['id'], 'Original typed display name',
        )
    open_account(page, workspace)
    expect(page.locator('#invite-form')).not_to_be_visible()
    expect(page.locator('#business-form')).not_to_be_visible()
    expect(page.locator('#suspension-form')).not_to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'accounts-crew-mobile.png'), full_page=True)
    page.goto(workspace['base_url'] + '/inventory.html')
    page.wait_for_url('**/crew.html')


def test_named_manager_without_legacy_id_reviews_operations(page, named_workspace, seed_report, complete_jobs):
    workspace = named_workspace
    seed_report(workspace['stores'][0]['id'], 'Named team report', 'The named account can read existing reporting.')
    complete_jobs()
    login_named(page, workspace, 'manager')
    expect(page.locator('.report-row').first).to_contain_text('Named team report')
    page.locator('#heads-up-update').click()
    page.locator('#heads-up-input').fill('Named manager handoff')
    page.locator('#heads-up-save').click()
    expect(page.locator('#manager-heads-up')).to_have_text('Named manager handoff')
    with db_connection() as connection:
        assert connection.execute('SELECT legacy_manager_id FROM account_users WHERE id=%s', (workspace['users']['manager'],)).fetchone()[0] is None
    open_account(page, workspace)
    expect(page.locator('#invite-form')).to_be_visible()
    expect(page.locator('#business-form')).not_to_be_visible()
    expect(page.locator('#suspension-form')).not_to_be_visible()
    expect(page.locator('#ownership-form')).not_to_be_visible()


def test_invitation_reissue_activation_and_replay(page, named_workspace):
    workspace = named_workspace
    login_named(page, workspace, 'owner')
    open_account(page, workspace)
    page.locator('#invite-username').fill('new-teammate')
    page.locator('#invite-display-name').fill('New Teammate')
    page.locator('#invite-role').select_option('crew')
    page.locator('#invite-form button[type=submit]').click()
    expect(page.locator('#invitation-code')).not_to_have_value('')
    old_token = page.locator('#invitation-code').input_value()
    page.locator('#dismiss-invitation').click()
    row = page.locator('#team-list [data-user-id]').filter(has_text='New Teammate')
    page.once('dialog', lambda dialog: dialog.accept())
    row.get_by_role('button', name='Reissue invitation').click()
    expect(page.locator('#invitation-code')).not_to_have_value('')
    token = page.locator('#invitation-code').input_value()
    assert token != old_token
    assert BrowserApi(workspace['base_url']).request('POST', '/api/accounts/activate', payload={'token': old_token, 'password': workspace['password']}).status == 400
    assert token not in page.url
    assert page.evaluate('JSON.stringify({...localStorage,...sessionStorage})') == '{}'
    page.locator('#account-logout').click()
    page.wait_for_url('**/')
    page.goto(workspace['base_url'] + '/activate.html')
    page.locator('#activation-token').fill(token)
    page.locator('#activation-password').fill(workspace['password'])
    page.locator('#activation-confirm').fill(workspace['password'])
    page.locator('#activation-form button[type=submit]').click()
    page.wait_for_url('**/crew.html')
    status = BrowserApi(workspace['base_url']).request('GET', '/api/accounts/status', cookie=named_cookie(page)).json()
    assert status['actor']['username'] == 'new-teammate'
    assert BrowserApi(workspace['base_url']).request('POST', '/api/accounts/activate', payload={'token': token, 'password': workspace['password']}).status == 400


def test_manager_can_grant_crew_inventory_and_revoke_local_membership(page, named_workspace):
    workspace = named_workspace
    previous = workspace['accounts'].login('market-store', 'account-crew', workspace['password'], client_key='browser-existing').token
    login_named(page, workspace, 'manager')
    open_account(page, workspace)
    row = page.locator(f"#team-list [data-user-id='{workspace['users']['crew']}']")
    row.get_by_role('button', name='Edit access').click()
    page.locator('#member-capabilities input[value="inventory.view"]').check()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#membership-form button[type=submit]').click()
    expect(page.locator('#team-status')).to_contain_text('Store permissions updated')
    row.get_by_role('button', name='Edit access').click()
    expect(page.locator('#member-capabilities input[value="inventory.view"]')).to_be_checked()
    with db_connection() as connection:
        assert 'inventory.view' in connection.execute('SELECT capabilities FROM account_store_memberships WHERE user_id=%s', (workspace['users']['crew'],)).fetchone()[0]
    assert BrowserApi(workspace['base_url']).request('GET', '/api/accounts/status', cookie='shiftly_account_session=' + previous).status == 401
    page.once('dialog', lambda dialog: dialog.accept())
    row.get_by_role('button', name='Remove access').click()
    expect(row).to_contain_text(re.compile('Revoked|Removed', re.I))
    with db_connection() as connection:
        assert connection.execute('SELECT state FROM account_store_memberships WHERE user_id=%s', (workspace['users']['crew'],)).fetchone()[0] == 'revoked'


def test_password_change_and_operator_recovery_invalidate_old_sessions(page, named_workspace):
    workspace = named_workspace
    login_named(page, workspace, 'crew')
    original_cookie = named_cookie(page)
    open_account(page, workspace)
    page.locator('#current-password').fill(workspace['password'])
    page.locator('#new-password').fill('changed-browser-password-456')
    page.locator('#confirm-password').fill('changed-browser-password-456')
    page.locator('#password-form button[type=submit]').click()
    page.wait_for_url('**/')
    api = BrowserApi(workspace['base_url'])
    assert api.request('GET', '/api/accounts/status', cookie=original_cookie).status == 401
    assert api.request('POST', '/api/accounts/login', payload={'storeCode': 'market-store', 'username': 'account-crew', 'password': workspace['password']}).status == 401
    login_named(page, workspace, 'crew', password='changed-browser-password-456')
    changed_cookie = named_cookie(page)
    recovery = workspace['accounts'].issue_password_reset(user_id=workspace['users']['crew'], reason='Synthetic verified browser recovery')
    page.goto(workspace['base_url'] + '/activate.html')
    page.locator('#activation-mode').select_option('recovery')
    page.locator('#activation-token').fill(recovery['token'])
    page.locator('#activation-password').fill('recovered-browser-password-789')
    page.locator('#activation-confirm').fill('recovered-browser-password-789')
    page.locator('#activation-form button[type=submit]').click()
    page.wait_for_url('**/')
    assert api.request('GET', '/api/accounts/status', cookie=changed_cookie).status == 401
    assert api.request('POST', '/api/accounts/reset-password', payload={'token': recovery['token'], 'password': workspace['password']}).status == 400
    login_named(page, workspace, 'crew', password='recovered-browser-password-789')


def test_store_selection_rotates_session_and_clears_previous_team(page, named_workspace):
    workspace = named_workspace
    login_named(page, workspace, 'owner')
    original_cookie = named_cookie(page)
    open_account(page, workspace)
    expect(page.locator('#team-list')).to_contain_text('Account Crew')
    page.locator('#store-select').select_option(str(workspace['stores'][1]['id']))
    page.locator('#switch-store').click()
    expect(page.locator('#account-profile')).to_contain_text('Harbor')
    expect(page.locator('#team-list')).not_to_contain_text('Account Crew')
    assert BrowserApi(workspace['base_url']).request('GET', '/api/accounts/status', cookie=original_cookie).status == 401
    page.goto(workspace['base_url'] + '/crew.html')
    page.locator('#employee').fill('Owner at Harbor')
    page.locator('#shift').select_option('closing')
    page.locator('#notes').fill('The harbor team finished stocking the shelves and checked the handoff.')
    page.locator('#generate-button').click()
    expect(page.locator('#result-content')).to_be_visible()
    with db_connection() as connection:
        assert connection.execute('SELECT store_id,actor_user_id FROM reports').fetchone() == (workspace['stores'][1]['id'], workspace['users']['owner'])


def test_inventory_only_admin_has_usable_navigation_and_logout_all(page, named_workspace, tmp_path):
    workspace = named_workspace
    page.set_viewport_size({'width': 390, 'height': 844})
    other = workspace['accounts'].login('market-store', 'account-admin', workspace['password'], client_key='other-browser').token
    login_named(page, workspace, 'admin')
    expect(page.locator('#account-profile')).to_contain_text('Market Street')
    expect(page.locator('#invite-form')).not_to_be_visible()
    page.goto(workspace['base_url'] + '/inventory.html')
    expect(page.get_by_role('heading', name=re.compile('Inventory'))).to_be_visible()
    assert page.locator('button', has_text=re.compile('Add product|Receive|Post stock|Submit count', re.I)).count() == 0
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.screenshot(path=str(tmp_path / 'inventory-mobile.png'), full_page=True)
    page.goto(workspace['base_url'] + '/accounts.html')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#logout-all').click()
    page.wait_for_url('**/')
    assert BrowserApi(workspace['base_url']).request('GET', '/api/accounts/status', cookie='shiftly_account_session=' + other).status == 401


def test_owner_cutover_disables_shared_crew_without_disabling_named_accounts(page, named_workspace):
    workspace = named_workspace
    api = BrowserApi(workspace['base_url'])
    shared = api.request('POST', '/api/auth/login', payload={'storeCode': 'market-store', 'role': 'crew', 'password': 'shared-password-123'})
    assert shared.status == 200
    shared_cookie = shared.cookie('shiftly_crew_session')
    login_named(page, workspace, 'owner')
    open_account(page, workspace)
    page.get_by_text('Require individual crew sign-in', exact=True).click()
    page.once('dialog', lambda dialog: dialog.accept())
    with page.expect_response(lambda response: response.url.endswith('/api/accounts/cutover')) as cutover:
        page.locator('#cutover-button').click()
    assert cutover.value.status == 200
    assert api.request('GET', '/api/auth/status', cookie=shared_cookie).json()['authenticated'] is False
    assert api.request('POST', '/api/auth/login', payload={'storeCode': 'market-store', 'role': 'crew', 'password': 'shared-password-123'}).status == 401
    assert api.request('POST', '/api/accounts/login', payload={'storeCode': 'market-store', 'username': 'account-crew', 'password': workspace['password']}).status == 200


def test_owner_business_delegation_suspension_and_transfer(page, named_workspace, tmp_path):
    workspace = named_workspace
    login_named(page, workspace, 'owner')
    old_owner_cookie = named_cookie(page)
    open_account(page, workspace)
    expect(page.locator('#team-list')).to_contain_text('Account Manager')
    page.screenshot(path=str(tmp_path / 'accounts-owner-desktop.png'), full_page=True)
    page.get_by_text('Delegate business authority', exact=True).click()
    page.locator('#business-user').select_option(str(workspace['users']['manager']))
    page.locator('#business-role').select_option('admin')
    page.locator('#business-capabilities input[value="catalog.manage"]').check()
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#business-form button[type=submit]').click()
    expect(page.locator('#owner-status')).to_contain_text('Business authority updated')
    with db_connection() as connection:
        assert connection.execute('SELECT role,capabilities FROM business_memberships WHERE user_id=%s', (workspace['users']['manager'],)).fetchone() == ('admin', ['catalog.manage'])
    page.get_by_text('Suspend or restore an account', exact=True).click()
    page.locator('#suspension-user').select_option(str(workspace['users']['crew']))
    page.locator('#suspension-reason').fill('Synthetic browser account review')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#suspension-form button[type=submit]').click()
    expect(page.locator('#owner-status')).to_contain_text('Account suspended')
    with db_connection() as connection:
        assert connection.execute('SELECT state FROM account_users WHERE id=%s', (workspace['users']['crew'],)).fetchone()[0] == 'suspended'
    page.locator('#suspension-user').select_option(str(workspace['users']['crew']))
    page.locator('#suspension-action').select_option('restore')
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#suspension-form button[type=submit]').click()
    expect(page.locator('#owner-status')).to_contain_text('Account restored')
    page.get_by_text('Transfer your ownership', exact=True).click()
    page.locator('#ownership-user').select_option(str(workspace['users']['manager']))
    page.once('dialog', lambda dialog: dialog.accept())
    page.locator('#ownership-form button[type=submit]').click()
    page.wait_for_url('**/')
    api = BrowserApi(workspace['base_url'])
    assert api.request('GET', '/api/accounts/status', cookie=old_owner_cookie).status == 401
    login_named(page, workspace, 'manager')
    status = api.request('GET', '/api/accounts/status', cookie=named_cookie(page)).json()
    assert status['actor']['role'] == 'owner'
    open_account(page, workspace)
    expect(page.locator('#owner-section')).to_be_visible()
