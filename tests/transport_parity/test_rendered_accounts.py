"""Render the native account screens with real authorization and PostgreSQL."""
import json
import os
import re
from pathlib import Path
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse, parse_qs

import pytest
from playwright.sync_api import expect
from database import db_connection
from tests.transport_parity.test_mobile_api import mobile

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope='session')
def accounts_bundle(tmp_path_factory):
    out=tmp_path_factory.mktemp('native-accounts')/'app.js'
    result=subprocess.run([os.environ.get('NATIVE_TEST_NODE','node'),str(ROOT/'apps/mobile/tests/rendered/build.mjs'),str(out),'tests/rendered/accounts-entry.tsx'],
                          cwd=ROOT/'apps/mobile',capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    return out.read_bytes()

@pytest.fixture
def native_accounts(mobile,accounts_bundle):
    m=mobile
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def run(self):
            path=urlparse(self.path).path
            if path.startswith('/api/mobile/'):
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                response=m.client.request(self.command,self.path,headers=dict(self.headers),content=body)
                self.send_response(response.status_code);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.content)
            elif path=='/app.js':
                self.send_response(200);self.send_header('Content-Type','text/javascript');self.end_headers();self.wfile.write(accounts_bundle)
            else:
                role=parse_qs(urlparse(self.path).query).get('as',['crew' if 'crew' in self.path else 'owner'])[0]
                token=m.login(role) if path in ('/team/invite','/accounts','/store','/team','/team/access','/heads-up','/today') else None
                html='<meta name="viewport" content="width=device-width, initial-scale=1"><div id="root"></div>'
                html+='<script>window.__testToken='+json.dumps(token)+'</script><script src="/app.js"></script>'
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html.encode())
        do_GET=run
        do_POST=run
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',m
    server.shutdown();server.server_close();thread.join(timeout=5)


def test_native_invitation_link_opens_bound_account_and_activates_once(page,native_accounts):
    base,m=native_accounts;page.set_viewport_size({'width':390,'height':844})
    page.goto(base+'/team/invite')
    page.get_by_label('Username',exact=True).fill('new.native.person')
    page.get_by_label('Display name',exact=True).fill('New Native Person')
    expect(page.get_by_role('radio',name='Manager',exact=True)).to_have_count(0)
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('button',name='Create invitation',exact=True).click()
    link=page.get_by_label('Invitation link',exact=True)
    expect(link).to_be_visible()
    secret=parse_qs(urlparse(link.inner_text()).fragment)['invitation'][0]
    page.goto(base+'/activate#invitation='+secret)
    expect(page.get_by_text('Join mobile-first as @new.native.person. Your account starts as crew.',exact=True)).to_be_visible()
    assert secret not in page.url
    assert page.evaluate('JSON.stringify({...localStorage,...sessionStorage})')=='{}'
    page.get_by_label('New password',exact=True).fill('individual-password')
    page.get_by_label('Confirm new password',exact=True).fill('individual-password')
    page.get_by_role('button',name='Activate my account',exact=True).click()
    expect(page.get_by_text('New Native Person',exact=True)).to_be_visible()
    assert m.send('POST','/api/mobile/accounts/activate',json={'token':secret,'password':'another-password','role':'owner'}).status_code==400


def test_native_common_login_has_no_store_code_or_role_selector(page,native_accounts):
    base,m=native_accounts;page.goto(base+'/sign-in')
    expect(page.get_by_label('Store code',exact=True)).to_have_count(0)
    expect(page.get_by_role('radio')).to_have_count(0)
    page.get_by_label('Username',exact=True).fill('crew')
    page.get_by_label('Password',exact=True).fill(m.password)
    page.get_by_role('button',name='Sign in',exact=True).click()
    expect(page.get_by_text('Mobile crew',exact=True)).to_be_visible()


def test_native_manager_account_has_no_store_switch(page,native_accounts):
    base,m=native_accounts
    m.accounts.set_membership(m.login(),user_id=m.users['crew'],role='manager')
    page.goto(base+'/accounts?crew')
    expect(page.get_by_text('Mobile crew',exact=True).first).to_be_visible()
    expect(page.get_by_role('button',name='Switch store',exact=False)).to_have_count(0)


def account_screenshot(page, name):
    if os.environ.get('ACCOUNT_SCREENSHOT_DIR'):
        page.screenshot(path=str(Path(os.environ['ACCOUNT_SCREENSHOT_DIR'])/name),full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')


def test_native_sign_out_requires_confirmation_and_cancel_preserves_session(page,native_accounts):
    base,m=native_accounts;page.set_viewport_size({'width':390,'height':844});page.goto(base+'/accounts')
    expect(page.get_by_role('button',name='Permissions',exact=True)).to_be_visible()
    account_screenshot(page,'account-settings-phone.png')
    logouts=[]
    page.on('request',lambda request:logouts.append(request.url) if request.url.endswith('/accounts/logout') else None)
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.get_by_role('button',name='Cancel',exact=True)).to_be_visible()
    assert not logouts
    account_screenshot(page,'sign-out-confirmation-phone.png')
    page.get_by_role('button',name='Cancel',exact=True).click()
    expect(page.get_by_role('button',name='Permissions',exact=True)).to_be_visible()
    assert not logouts
    page.get_by_role('button',name='Sign out',exact=True).click()
    page.get_by_role('button',name='Cancel',exact=True).wait_for()
    page.get_by_role('button',name='Sign out',exact=True).click()
    expect(page.get_by_role('button',name='Sign in',exact=True)).to_be_visible()
    assert len(logouts)==1


@pytest.mark.parametrize('role,visible',[('owner',True),('manager',True),('crew',False),('viewer',False)])
def test_native_store_tab_and_direct_route_use_the_requested_roles(page,native_accounts,role,visible):
    base,m=native_accounts
    if role=='manager':
        m.accounts.set_membership(m.login(),user_id=m.users['crew'],role='manager')
    username='crew' if role=='manager' else role
    page.set_viewport_size({'width':390,'height':844});page.goto(base+'/store?as='+username)
    navigation=page.get_by_role('navigation',name='Main navigation')
    expect(navigation.get_by_role('button',name='Account',exact=True)).to_be_visible()
    expect(navigation.get_by_role('button',name='Store',exact=True)).to_have_count(1 if visible else 0)
    if visible:
        build=page.get_by_role('button',name=re.compile('^Build team',re.I))
        expect(build).to_be_visible()
        owner=page.get_by_role('button',name=re.compile('owner tools',re.I))
        if role=='manager':
            expect(build).to_be_disabled();expect(owner).to_be_disabled()
        else:
            expect(owner).to_be_enabled()
            assert navigation.get_by_role('button').all_text_contents()==['Today','Reports','Inventory','Store','Account']
            account_screenshot(page,'store-hub-phone.png')
    else:
        expect(page.get_by_text('Store management is available to store managers and business owners.',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name=re.compile('owner tools',re.I))).to_have_count(0)


def test_native_member_dropdown_orders_recent_sign_ins_and_manages_one_member(page,native_accounts):
    base,m=native_accounts;owner_token=m.login()
    m.accounts.invite(owner_token,username='a.pending',display_name='Pending Person')
    page.set_viewport_size({'width':390,'height':844});page.goto(base+'/team')
    expect(page.get_by_role('button',name='Choose a team member',exact=True)).to_be_visible()
    m.login('crew')
    page.get_by_role('button',name='Refresh team',exact=True).click()
    page.get_by_role('button',name='Choose a team member',exact=True).click()
    choices=page.get_by_role('button',name=re.compile('^Choose (Mobile|Pending)'))
    expect(choices).to_have_count(4)
    assert [button.get_attribute('aria-label') for button in choices.all()]==[
        'Choose Mobile crew','Choose Mobile owner','Choose Pending Person','Choose Mobile viewer']
    account_screenshot(page,'team-dropdown-phone.png')
    page.get_by_label('Find a team member',exact=True).fill('crew')
    expect(choices).to_have_count(1)
    page.get_by_role('button',name='Choose Mobile crew',exact=True).click()
    expect(page.get_by_role('button',name='Manage Mobile crew',exact=True)).to_be_visible()
    expect(page.get_by_role('heading',name='Mobile owner',exact=True)).to_have_count(0)
    expect(page.get_by_text('Last signed in here',exact=False)).to_be_visible()
    account_screenshot(page,'selected-team-member-phone.png')
    page.get_by_role('button',name='Manage Mobile crew',exact=True).click()
    page.get_by_role('checkbox',name='Submit stock counts',exact=True).click()
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('button',name='Save store access',exact=True).click()
    expect(page.get_by_text('Store access saved. Existing sessions at this store have ended.',exact=True)).to_be_visible()
    with db_connection() as connection:
        assert 'counts.submit' in connection.execute('SELECT capabilities FROM account_store_memberships WHERE user_id=%s AND store_id=%s',(m.users['crew'],m.stores[0])).fetchone()[0]


def test_native_settings_preserve_authorized_switching_and_permissions(page,native_accounts):
    base,m=native_accounts;page.goto(base+'/accounts')
    page.get_by_role('button',name='Switch store',exact=True).click()
    page.once('dialog',lambda dialog:dialog.dismiss())
    page.get_by_role('button',name='Switch to mobile-second',exact=True).click()
    assert page.evaluate('window.__accountsTest.getSnapshot().actor.storeId')==m.stores[0]
    page.once('dialog',lambda dialog:dialog.accept())
    page.get_by_role('button',name='Switch to mobile-second',exact=True).click()
    expect(page.get_by_role('button',name='Permissions',exact=True)).to_be_visible()
    assert page.evaluate('window.__accountsTest.getSnapshot().actor.storeId')==m.stores[1]
    page.get_by_role('button',name='Permissions',exact=True).click()
    expect(page.get_by_text('Manage shared products',exact=True)).to_be_visible()



def test_native_administrator_keeps_team_building_without_store_tab(page,native_accounts):
    base,m=native_accounts;owner=m.login()
    m.accounts.set_business_membership(owner,user_id=m.users['viewer'],role='admin',capabilities=['memberships.manage','reports.submit'])
    m.accounts.set_membership(owner,user_id=m.users['viewer'],role='admin',capabilities=['memberships.manage','reports.submit'])
    page.goto(base+'/accounts?as=viewer')
    expect(page.get_by_role('navigation').get_by_role('button',name='Store',exact=True)).to_have_count(0)
    page.get_by_role('link',name='Team administration',exact=True).click()
    page.get_by_role('button',name='Build your team',exact=True).click()
    expect(page.get_by_role('button',name='Invite a new person',exact=True)).to_be_enabled()
    expect(page.get_by_role('button',name='Add an existing account',exact=True)).to_be_enabled()
    page.get_by_role('button',name='Invite a new person',exact=True).click()
    expect(page.get_by_label('Username',exact=True)).to_be_visible()



def test_native_store_sections_return_directly_to_store_despite_navigation_history(page,native_accounts):
    base,_=native_accounts;page.goto(base+'/store')
    navigation=page.get_by_role('navigation',name='Main navigation')
    navigation.get_by_role('button',name='Today',exact=True).click()
    navigation.get_by_role('button',name='Store',exact=True).click()
    # Visit Store Access first so later team pages have a previous sibling in history.
    sections=[('Store access','Store access'),
              ('Build team','Build team'),
              ('Team members','Team members'),
              ('Owner tools','Owner tools')]
    for action,title in sections:
        page.get_by_role('button',name=action,exact=True).click()
        expect(page.get_by_role('heading',name=title,exact=True)).to_be_visible()
        page.get_by_role('button',name='Back to store',exact=True).click()
        expect(page.get_by_role('heading',name='Store',exact=True)).to_be_visible()
        expect(page.get_by_role('button',name='Build team',exact=True)).to_be_visible()


def test_native_admin_team_back_returns_to_account_without_store_access(page,native_accounts):
    base,m=native_accounts;owner=m.login()
    m.accounts.set_business_membership(owner,user_id=m.users['viewer'],role='admin',capabilities=['memberships.manage','reports.submit'])
    m.accounts.set_membership(owner,user_id=m.users['viewer'],role='admin',capabilities=['memberships.manage','reports.submit'])
    page.goto(base+'/accounts?as=viewer')
    page.get_by_role('link',name='Team administration',exact=True).click()
    page.get_by_role('button',name='Back to account',exact=True).click()
    expect(page.get_by_role('button',name='Permissions',exact=True)).to_be_visible()
    expect(page.get_by_role('navigation').get_by_role('button',name='Store',exact=True)).to_have_count(0)
