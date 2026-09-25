"""Render the native account screens with real authorization and PostgreSQL."""
import json
import os
from pathlib import Path
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse, parse_qs

import pytest
from playwright.sync_api import expect
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
                token=m.login('crew' if 'crew' in self.path else 'owner') if path in ('/team/invite','/accounts') else None
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
    expect(page.get_by_text(f'Signed in as new.native.person at store {m.stores[0]}',exact=True)).to_be_visible()
    assert m.send('POST','/api/mobile/accounts/activate',json={'token':secret,'password':'another-password','role':'owner'}).status_code==400


def test_native_common_login_has_no_store_code_or_role_selector(page,native_accounts):
    base,m=native_accounts;page.goto(base+'/sign-in')
    expect(page.get_by_label('Store code',exact=True)).to_have_count(0)
    expect(page.get_by_role('radio')).to_have_count(0)
    page.get_by_label('Username',exact=True).fill('crew')
    page.get_by_label('Password',exact=True).fill(m.password)
    page.get_by_role('button',name='Sign in',exact=True).click()
    expect(page.get_by_text(f'Signed in as crew at store {m.stores[0]}',exact=True)).to_be_visible()


def test_native_manager_account_has_no_store_switch(page,native_accounts):
    base,m=native_accounts
    m.accounts.set_membership(m.login(),user_id=m.users['crew'],role='manager')
    page.goto(base+'/accounts?crew')
    expect(page.get_by_text('Mobile crew',exact=True).first).to_be_visible()
    expect(page.get_by_role('button',name='Switch store',exact=False)).to_have_count(0)
