import http.server, os, subprocess, threading
from pathlib import Path
import pytest
from playwright.sync_api import expect

ROOT=Path(__file__).resolve().parents[2]; MOBILE=ROOT/'apps'/'mobile'
@pytest.fixture(scope='session')
def receiving_bundle(tmp_path_factory):
    output=tmp_path_factory.mktemp('receiving')/'app.js'; node=os.environ.get('NATIVE_TEST_NODE','node')
    subprocess.run([node,str(MOBILE/'tests/rendered/receiving-build.mjs'),str(output)],cwd=MOBILE,check=True); return output
@pytest.fixture(scope='session')
def receiving_url(receiving_bundle):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body=receiving_bundle.read_bytes() if self.path=='/app.js' else b'<!doctype html><style>html,body,#root{height:100%;margin:0}</style><div id="root"></div><script src="/app.js"></script>'
            self.send_response(200); self.send_header('Content-Type','text/javascript' if self.path=='/app.js' else 'text/html'); self.end_headers(); self.wfile.write(body)
        def log_message(self,*_args): pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler); thread=threading.Thread(target=server.serve_forever,daemon=True); thread.start()
    try: yield f'http://127.0.0.1:{server.server_port}'
    finally: server.shutdown(); thread.join()

def test_invoice_photo_is_explicitly_reviewed_before_draft_save(page,receiving_url):
    page.goto(receiving_url); page.get_by_role('button',name='Scan invoice').click()
    expect(page.get_by_role('heading',name='Frame the full invoice')).to_be_visible(); page.get_by_role('button',name='Take photo').click()
    expect(page.get_by_role('heading',name='Photo preview')).to_be_visible(); expect(page.get_by_text('configured AI provider',exact=False)).to_be_visible()
    page.get_by_role('button',name='Read invoice').click(); expect(page.get_by_role('button',name='Apply photo proposal')).to_be_visible()
    page.get_by_role('button',name='Apply photo proposal').click(); expect(page.get_by_label('Supplier')).to_have_value('Dairy Co'); expect(page.get_by_label('Invoice number')).to_have_value('00042')
    page.get_by_role('checkbox',name='Received: Milk').click()
    page.get_by_role('button',name='Save draft').click(); expect(page.get_by_text('1/60 lines',exact=False)).to_be_visible(); expect(page.get_by_role('button',name='Save draft')).to_be_disabled()

def test_add_cancel_does_not_leave_a_blank_line(page,receiving_url):
    page.goto(receiving_url); page.get_by_role('button',name='Add manually').click(); page.get_by_role('button',name='Add line').click()
    page.get_by_role('button',name='Cancel').click(); expect(page.get_by_text('No lines yet.')).to_be_visible(); expect(page.get_by_role('button',name='Save draft')).to_be_disabled()

def test_successive_blank_invoices_use_distinct_request_ids(page,receiving_url):
    page.goto(receiving_url); page.get_by_role('button',name='Add manually').click(); page.get_by_role('button',name='Back to invoices').click(); page.get_by_role('button',name='Add manually').click()
    ids=page.evaluate('window.__createRequestIds'); assert len(ids)==2 and ids[0]!=ids[1]

def test_matched_package_can_switch_to_loose_and_back(page,receiving_url):
    page.goto(receiving_url+'?scenario=package'); page.get_by_role('button',name='Edit line Milk case').click(); expect(page.get_by_text('Matched to Milk')).to_be_visible()
    page.get_by_role('button',name='Loose quantity',exact=False).click(); expect(page.get_by_role('button',name='✓ kg')).to_be_visible()
    page.get_by_role('button',name='10 kg case',exact=False).click(); expect(page.get_by_role('button',name='✓ package')).to_be_visible(); page.get_by_role('button',name='Save line').click(); page.get_by_role('button',name='Save draft').click()
    body=page.evaluate("JSON.parse(sessionStorage.getItem('saveBodies'))[0]"); assert body['lines'][0]['id']!='66666666-6666-4666-8666-666666666666'

def test_closed_invoice_is_read_only(page,receiving_url):
    page.goto(receiving_url+'?scenario=closed'); expect(page.get_by_text('read-only history',exact=False)).to_be_visible()
    expect(page.get_by_role('button',name='Edit line Milk case')).to_have_count(0); expect(page.get_by_role('checkbox')).to_have_count(0); expect(page.get_by_role('button',name='Add line')).to_have_count(0)

def test_retry_poll_preserves_unsaved_fields(page,receiving_url):
    page.goto(receiving_url+'?scenario=retry'); page.get_by_label('Supplier').fill('My unsaved supplier'); page.get_by_role('button',name='Retry photo reading').click()
    expect(page.get_by_role('button',name='Apply photo proposal')).to_be_visible(); expect(page.get_by_label('Supplier')).to_have_value('My unsaved supplier')

def test_cold_uncertain_retry_keeps_original_version_and_request_identity(page,receiving_url):
    page.goto(receiving_url+'?scenario=concurrency&version=1'); page.get_by_label('Supplier').fill('Cold draft'); page.get_by_role('button',name='Save draft').click()
    expect(page.get_by_text('Unable to confirm save')).to_be_visible(); first=page.evaluate("JSON.parse(sessionStorage.getItem('saveBodies'))[0]")
    page.goto(receiving_url+'?scenario=concurrency&version=2'); expect(page.get_by_label('Supplier')).to_have_value('Cold draft'); expect(page.get_by_text('newer invoice version',exact=False)).to_be_visible()
    page.get_by_role('button',name='Save draft').click(); expect(page.get_by_text('Unable to confirm save')).to_be_visible(); second=page.evaluate("JSON.parse(sessionStorage.getItem('saveBodies'))[1]")
    assert first['version']==second['version']==1; assert first['requestId']==second['requestId']
    saved=page.evaluate("sessionStorage.getItem('remembered:receiving.invoice.11111111-1111-4111-8111-111111111111')"); assert 'payload' not in saved; assert len(saved)<12_000
    page.get_by_label('Supplier').fill('Changed after retry'); page.get_by_role('button',name='Save draft').click(); third=page.evaluate("JSON.parse(sessionStorage.getItem('saveBodies'))[2]")
    assert third['requestId']!=second['requestId']; assert third['version']==1

def test_manual_invoice_drives_incoming_preview_and_close_removes_it(page,receiving_url):
    shots=os.environ.get('RECEIVING_SCREENSHOTS'); page.set_viewport_size({'width':390,'height':844}); page.goto(receiving_url+'?scenario=manual');
    if shots: Path(shots).mkdir(parents=True,exist_ok=True); page.screenshot(path=str(Path(shots)/'invoice-list.png'),full_page=True)
    page.get_by_role('button',name='Add manually').click()
    page.get_by_label('Supplier').fill('Dairy Co'); page.get_by_label('Invoice number').fill('INV-42'); page.get_by_role('button',name='Add line').click()
    page.get_by_label('Description').fill('Milk case'); page.get_by_label('Quantity').fill('2'); page.get_by_label('Product name or SKU').fill('milk'); page.get_by_role('button',name='Search catalog').click()
    page.get_by_role('button',name='Milk · MILK-01').click(); page.get_by_role('button',name='10 kg case',exact=False).click(); page.get_by_role('button',name='Save line').click()
    page.get_by_role('checkbox',name='Received: Milk case').click(); page.get_by_role('button',name='Save draft').click(); expect(page.get_by_role('button',name='Save draft')).to_be_disabled()
    if shots: page.screenshot(path=str(Path(shots)/'invoice-editor.png'),full_page=True)
    page.evaluate("window.__receivingGo('/incoming')"); expect(page.get_by_text('Milk',exact=True)).to_be_visible(); expect(page.get_by_text('kg · 20 received')).to_be_visible()
    if shots: page.screenshot(path=str(Path(shots)/'incoming.png'),full_page=True)
    row=page.get_by_text('Milk',exact=True).locator('..').locator('..'); expect(row.get_by_text('5',exact=True)).to_be_visible(); expect(row.get_by_text('20',exact=True)).to_be_visible(); expect(row.get_by_text('25',exact=True)).to_be_visible()
    page.evaluate("window.__receivingGo('/invoices/11111111-1111-4111-8111-111111111111')"); page.once('dialog',lambda dialog: dialog.accept()); page.get_by_role('button',name='Close invoice').click(); expect(page.get_by_role('heading',name='Invoices.')).to_be_visible()
    page.evaluate("window.__receivingGo('/incoming')"); expect(page.get_by_text('No incoming quantities')).to_be_visible()

def test_use_latest_count_resets_draft_to_new_server_version(page,receiving_url):
    page.goto(receiving_url+'?scenario=rebase'); page.get_by_role('button',name='Use latest count').click(); expect(page.get_by_role('button',name='Use latest count')).to_have_count(0)
    page.get_by_label('Supplier').fill('After rebase'); page.get_by_role('button',name='Save draft').click(); body=page.evaluate("JSON.parse(sessionStorage.getItem('saveBodies'))[0]")
    assert body['version']==2

def test_unavailable_photo_provider_disables_editor_and_direct_camera(page,receiving_url):
    page.goto(receiving_url+'?scenario=photo-unavailable'); expect(page.get_by_role('button',name='Scan invoice photo')).to_be_disabled(); expect(page.get_by_text('still enter and match',exact=False)).to_be_visible()
    page.evaluate("window.__receivingGo('/invoices/11111111-1111-4111-8111-111111111111/photo')"); expect(page.get_by_role('heading',name='Photo reading unavailable')).to_be_visible(); expect(page.get_by_role('button',name='Take photo')).to_have_count(0)
