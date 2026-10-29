"""Actual native inventory components in Chromium; backend persistence is real.

Only navigation, native dialogs and device credential storage are test adapters.
This does not establish iPhone/Android device acceptance.
"""
import json
import os
import re
from pathlib import Path
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from urllib.parse import urlparse

import pytest
from playwright.sync_api import expect

ROOT=Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session')
def inventory_bundle(tmp_path_factory):
    out=tmp_path_factory.mktemp('inventory-render')/'app.js'
    result=subprocess.run([os.environ.get('NATIVE_TEST_NODE','node'),str(ROOT/'apps/mobile/tests/rendered/build.mjs'),str(out)],
                          cwd=ROOT/'apps/mobile',capture_output=True,text=True,timeout=60)
    assert result.returncode==0,result.stderr
    return out.read_bytes()


@pytest.fixture
def native_inventory(inventory,inventory_bundle):
    i=inventory
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*_): pass
        def run(self):
            if self.path.startswith('/api/mobile/'):
                body=self.rfile.read(int(self.headers.get('Content-Length','0')))
                response=i.client.request(self.command,self.path,headers=dict(self.headers),content=body)
                self.send_response(response.status_code)
                self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(response.content)
            elif self.path=='/app.js':
                self.send_response(200);self.send_header('Content-Type','text/javascript');self.end_headers();self.wfile.write(inventory_bundle)
            else:
                role='crew' if 'crew' in urlparse(self.path).query else 'owner'
                html='<meta name="viewport" content="width=device-width, initial-scale=1"><div id="root"></div>'
                html+='<script>window.__testToken='+json.dumps(i.tokens[role])+'</script><script src="/app.js"></script>'
                self.send_response(200);self.send_header('Content-Type','text/html');self.end_headers();self.wfile.write(html.encode())
        do_GET=run
        do_POST=run
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    yield f'http://127.0.0.1:{server.server_port}',i
    server.shutdown();server.server_close();thread.join(timeout=5)


def test_rendered_owner_creates_product_and_shelf_then_reopens_placement(page,native_inventory):
    url,i=native_inventory;page.set_viewport_size({'width':390,'height':844});page.goto(url)
    page.get_by_role('button',name='Open company catalog',exact=True).click()
    page.get_by_role('button',name='Add product',exact=True).click()
    page.get_by_label('Product name',exact=True).fill('White Quella')
    page.get_by_label('SKU',exact=True).fill('000184')
    page.get_by_role('button',name='Kilograms',exact=True).click()
    expect(page.get_by_role('button',name='Millilitres',exact=False)).to_have_count(0)
    expect(page.get_by_role('button',name='Litres',exact=False)).to_have_count(0)
    page.get_by_label('Full container amount (kg)',exact=True).fill('6')
    expect(page.get_by_text('One full container = 6 kg = 6000 g.',exact=True)).to_be_visible()
    page.get_by_role('button',name='Create product',exact=True).click()
    expect(page.get_by_role('button',name='Save company product',exact=True)).to_be_visible()
    page.get_by_role('button',name='Back to catalog',exact=True).first.click()
    page.get_by_role('button',name='Back to inventory',exact=True).click()
    page.get_by_role('button',name='Open shelves',exact=True).click()
    page.get_by_label('New shelf name',exact=True).fill('Back freezer top')
    page.get_by_role('button',name='Create shelf',exact=True).click()
    page.get_by_role('button',name='Assign White Quella',exact=True).click()
    expect(page.get_by_role('button',name='Remove White Quella from shelf',exact=True)).to_be_visible()
    expect(page.get_by_label('Shelf name',exact=True)).to_have_count(0)
    page.get_by_role('button',name='Back to Open Shelves',exact=True).click()
    page.get_by_role('button',name='Edit shelf name: Back freezer top',exact=True).click()
    expect(page.get_by_role('heading',name='Edit shelf name',exact=True)).to_be_visible()
    page.get_by_label('Shelf name',exact=True).fill('Discard this shelf edit')
    page.get_by_role('button',name='Cancel',exact=True).click()
    expect(page.get_by_label('Shelf name',exact=True)).to_have_count(0)
    page.get_by_role('button',name='Edit shelf name: Back freezer top',exact=True).click()
    expect(page.get_by_label('Shelf name',exact=True)).to_have_value('Back freezer top')
    page.get_by_label('Shelf name',exact=True).fill('Back freezer middle')
    page.get_by_role('button',name='Save',exact=True).click()
    expect(page.get_by_role('button',name='Open Back freezer middle',exact=True)).to_be_visible()
    expect(page.get_by_label('Shelf name',exact=True)).to_have_count(0)
    page.get_by_role('button',name='Open Back freezer middle',exact=True).click()
    expect(page.get_by_role('button',name='Remove White Quella from shelf',exact=True)).to_be_visible()

    if os.environ.get('INVENTORY_SCREENSHOT_DIR'):
        page.screenshot(path=str(Path(os.environ['INVENTORY_SCREENSHOT_DIR'])/'shelf-phone.png'),full_page=True)
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    expect(page.get_by_role('button',name='Remove White Quella from shelf',exact=True)).to_be_visible()
    page.evaluate('(id)=>window.__inventoryTest.switchStore(id)',i.stores[1])
    expect(page.get_by_role('alert').filter(has_text='not available in your current workspace')).to_be_visible()
    page.get_by_role('button',name='Back to Open Shelves',exact=True).click()
    page.get_by_role('button',name='Back to inventory',exact=True).click()
    page.get_by_role('button',name='Open company catalog',exact=True).click()
    expect(page.get_by_role('button',name='View product: White Quella',exact=True)).to_be_visible()
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_products').fetchone()[0]==1
        assert str(c.execute('SELECT container_amount FROM inventory_products').fetchone()[0])=='6'
        assert c.execute('SELECT count(*) FROM inventory_shelf_products WHERE active').fetchone()[0]==1


def test_rendered_duplicate_and_stale_edits_preserve_form_then_archive_restore(page,native_inventory):
    url,i=native_inventory;page.set_viewport_size({'width':1024,'height':900});page.goto(url)
    f={'requestId':'11111111-1111-4111-8111-111111111111','expectedStoreId':i.stores[0],'name':'Milk','sku':'001','baseUnit':'kg'}
    p=i.service.create_product(i.tokens['owner'],f)
    page.get_by_role('button',name='Open company catalog',exact=True).click()
    page.get_by_role('button',name='Add product',exact=True).click()
    page.get_by_label('Product name',exact=True).fill('My draft')
    page.get_by_label('SKU',exact=True).fill('001')
    page.get_by_role('button',name='Create product',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('already in use')
    expect(page.get_by_label('Product name',exact=True)).to_have_value('My draft')
    page.get_by_role('button',name='Cancel and discard draft',exact=True).click()
    page.get_by_role('button',name='View product: Milk',exact=True).click()
    expect(page.get_by_label('Product name',exact=True)).to_have_value('Milk')
    i.service.edit_product(i.tokens['owner'],p['id'],{'requestId':'22222222-2222-4222-8222-222222222222','expectedStoreId':i.stores[0],'name':'New Milk','version':1,'sku':'002'})
    page.get_by_label('Product name',exact=True).fill('Unsaved edit')
    page.get_by_role('button',name='Save company product',exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('record changed')
    expect(page.get_by_label('Product name',exact=True)).to_have_value('Unsaved edit')
    page.get_by_role('button',name='Discard edits and reload',exact=True).click()
    expect(page.get_by_label('Product name',exact=True)).to_have_value('New Milk')
    if os.environ.get('INVENTORY_SCREENSHOT_DIR'):
        page.screenshot(path=str(Path(os.environ['INVENTORY_SCREENSHOT_DIR'])/'product-tablet.png'),full_page=True)
    page.on('dialog',lambda d:d.accept())
    page.get_by_role('button',name='Archive product',exact=True).click()
    expect(page.get_by_role('button',name='Restore product',exact=True)).to_be_visible()
    page.get_by_role('button',name='Restore product',exact=True).click()
    expect(page.get_by_role('button',name='Archive product',exact=True)).to_be_visible()
    page.evaluate('window.__inventoryTest.lock()')
    expect(page.get_by_text('Workspace locked',exact=True)).to_be_visible()
    expect(page.get_by_label('Product name',exact=True)).to_have_count(0)


def test_rendered_crew_sees_catalog_without_catalog_or_shelf_mutations(page,native_inventory):
    url,i=native_inventory;page.goto(url+'/?crew')
    page.get_by_role('button',name='Open company catalog',exact=True).click()
    expect(page.get_by_text('Ask an owner or catalog administrator',exact=False)).to_be_visible()
    expect(page.get_by_role('button',name='Add product',exact=True)).to_have_count(0)
    page.get_by_role('button',name='Back to inventory',exact=True).click()
    page.get_by_role('button',name='Open shelves',exact=True).click()
    expect(page.get_by_role('button',name='Create shelf',exact=True)).to_have_count(0)


def test_rendered_existing_product_size_and_alphabetical_search(page, native_inventory):
    from uuid import uuid4
    url, i = native_inventory
    products = []
    for name, measurement in (
        ('White Quella', {'baseUnit': 'kg'}),
        ('almond paste', {'baseUnit': 'kg', 'containerAmount': '6'}),
        ('Banana topping', {'baseUnit': 'each', 'containerAmount': '12'}),
        ('Low-Heat Non-Fat Dry Milk', {'baseUnit': 'kg', 'containerAmount': '50', 'containerUnit': 'lb'}),
    ):
        products.append(i.service.create_product(i.tokens['owner'], {
            'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
            'name': name, 'sku': str(uuid4()), **measurement}))
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url)
    page.get_by_role('button', name='Open company catalog', exact=True).click()
    rows = page.get_by_role('button', name=re.compile('^View product: '))
    expect(rows).to_have_count(4)
    assert [row.get_attribute('aria-label') for row in rows.all()] == [
        'View product: almond paste', 'View product: Banana topping',
        'View product: Low-Heat Non-Fat Dry Milk', 'View product: White Quella']
    for name, size in (('White Quella', 'Not set'), ('almond paste', '6 kg'),
                       ('Banana topping', '12 items'), ('Low-Heat Non-Fat Dry Milk', '50 lbs')):
        expect(page.get_by_role('button', name=f'View product: {name}', exact=True).get_by_text(size, exact=True)).to_be_visible()
    for width in (320, 390, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        # Resizing crosses Screen's phone/tablet inset breakpoint. Wait for the
        # whole layout, then measure all targets in one browser frame.
        page.wait_for_function('''() => {
            const boxes = [...document.querySelectorAll('[aria-label^="Change measurement: "]')]
                .map(element => element.getBoundingClientRect());
            const key = JSON.stringify([innerWidth, ...boxes.map(b => [b.x, b.y, b.width, b.height])]);
            if (window.__catalogLayout?.key !== key) {
                window.__catalogLayout = { key, since: performance.now() };
                return false;
            }
            return boxes.length === 4 && performance.now() - window.__catalogLayout.since > 150;
        }''')
        actions = page.get_by_role('button', name=re.compile('^Change measurement: '))
        boxes = actions.evaluate_all('(elements) => elements.map(element => { const b = element.getBoundingClientRect(); return {x:b.x,width:b.width,height:b.height}; })')
        assert all(box['width'] >= 44 and box['height'] >= 44 for box in boxes)
        assert max(box['x'] for box in boxes) - min(box['x'] for box in boxes) < 1
        if directory := os.environ.get('INVENTORY_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(directory)/f'catalog-compact-{width}.png'), full_page=True)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_label('Find a product or SKU', exact=True).fill('white')
    page.get_by_role('button', name='Search catalog', exact=True).click()
    expect(page.get_by_role('button', name='View product: almond paste', exact=True)).to_have_count(0)
    page.get_by_role('button', name='View product: White Quella', exact=True).click()
    page.get_by_role('button', name='Change measurement: White Quella', exact=True).click()
    amount = page.get_by_label('Full container amount (kg)', exact=True)
    expect(amount).to_have_value('')
    amount.fill('6')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('button', name='Close measurement editor', exact=True)).to_have_count(0)
    expect(page.get_by_text('6 kg', exact=True)).to_be_visible()
    saved = i.service.product(i.tokens['owner'], products[0]['id'])
    assert saved['containerAmount'] == '6' and saved['sku'] == products[0]['sku']
    assert saved['baseUnit'] == 'kg' and saved['version'] == 2
    page.get_by_role('button', name='Back to catalog', exact=True).first.click()
    page.get_by_role('button', name='Back to inventory', exact=True).click()
    page.get_by_role('button', name='Open shelves', exact=True).click()
    page.get_by_label('New shelf name', exact=True).fill('Alphabetical picker')
    page.get_by_role('button', name='Create shelf', exact=True).click()
    expect(page.get_by_role('button', name='Assign White Quella', exact=True)).to_be_visible()
    choices = page.get_by_role('button', name=re.compile('^Assign '))
    assert [item.get_attribute('aria-label') for item in choices.all()] == [
        'Assign almond paste', 'Assign Banana topping', 'Assign Low-Heat Non-Fat Dry Milk', 'Assign White Quella']
