"""Rendered native production journeys against the real isolated service."""
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse
from uuid import uuid4

import pytest
from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields, observe_all, post, start
from tests.inventory_services.test_rendered_native import ROOT, inventory_bundle, native_inventory


def production(i):
    return i.client.app.state.context.services.production


def screenshot(page, name, *, full_page=True):
    directory = os.environ.get('PRODUCTION_SCREENSHOT_DIR')
    if directory:
        page.screenshot(path=str(Path(directory) / name), full_page=full_page, animations='disabled')
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def stocked_product(i, name='Cocoa powder', sku='COCOA-1', amount='20'):
    product = i.service.create_product(i.tokens['owner'], fields(i, name=name, sku=sku, baseUnit='kg'))
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Production shelf'))
    i.service.place(i.tokens['owner'], shelf['id'], product['id'], fields(i, version=shelf['version'], active=True))
    post(i, observe_all(i, start(i), amount=amount))
    return product


def recipe(i, product, name='Chocolate base', amount='2', unit='kg'):
    return production(i).create_recipe(i.tokens['owner'], fields(i, name=name, yieldAmount='1', yieldUnit='batch', instructions='Mix until smooth.',
        ingredients=[{'productId': product['id'], 'amount': amount, 'unit': unit}]))


def test_rendered_recipe_create_and_production_review_confirm(page, native_inventory):
    url, i = native_inventory
    product = stocked_product(i)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url + '/production/recipes')
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Save Recipe', exact=True)).to_have_count(0)
    page.get_by_role('button', name='New Recipe', exact=True).click()
    page.get_by_label('Recipe name', exact=True).fill('Chocolate base')
    page.get_by_role('button', name='Recipe yield', exact=True).click()
    page.get_by_role('radio', name='6 kg', exact=True).click()
    expect(page.get_by_label('Yield unit', exact=True)).to_have_count(0)
    # Footer actions must fit both small phones and wider/short landscape windows.
    for width, height in ((320, 640), (768, 900), (1024, 768), (1440, 900), (844, 390), (568, 320)):
        page.set_viewport_size({'width': width, 'height': height})
        page.wait_for_function('''() => {
            const action = document.querySelector('[aria-label="Save Recipe"]');
            if (!action) return false;
            const box = action.getBoundingClientRect();
            const key = [window.innerWidth, window.innerHeight, box.x, box.y, box.width, box.height].join(':');
            const stable = window.__recipeLayoutTest;
            if (!stable || stable.key !== key) {
                window.__recipeLayoutTest = { key, since: performance.now() };
                return false;
            }
            return performance.now() - stable.since > 400
                && box.x >= 0 && box.right <= window.innerWidth && box.y >= 0 && box.bottom <= window.innerHeight;
        }''')
        actions = page.get_by_role('button', name='Save Recipe', exact=True)
        expect(actions).to_be_visible()
        box = actions.bounding_box()
        assert box and box['x'] >= 0 and box['x'] + box['width'] <= width
        assert box['y'] >= 0 and box['y'] + box['height'] <= height
        assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_label('Instructions (optional)', exact=True).fill('Mix until smooth.')
    page.get_by_role('button', name='Add Cocoa powder', exact=True).click()
    expect(page.get_by_role('button', name='Remove Cocoa powder', exact=True)).to_be_visible()
    page.get_by_role('button', name='Use g for Cocoa powder', exact=True).click()
    page.get_by_label('Amount', exact=True).fill('2000')
    screenshot(page, 'shiftly-production-recipe-phone.png', full_page=False)
    page.set_viewport_size({'width': 1024, 'height': 900})
    screenshot(page, 'shiftly-production-recipe-tablet.png', full_page=False)
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_role('button', name='Save Recipe', exact=True).click()
    expect(page.get_by_role('button', name='Edit Recipe', exact=True)).to_be_visible()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    made = production(i).recipes(i.tokens['owner'])['items'][0]
    assert (made['yieldAmount'], made['yieldUnit']) == ('6', 'kg')
    assert made['ingredients'][0]['unit'] == 'g' and made['ingredients'][0]['baseAmount'] == '2'

    page.goto(url + '/production/run')
    page.get_by_role('checkbox', name='Add Chocolate base', exact=True).click()
    page.get_by_role('button', name='Add one batch of Chocolate base', exact=True).click()
    page.get_by_role('button', name='Add one batch of Chocolate base', exact=True).click()
    expect(page.get_by_text('3', exact=True)).to_be_visible()
    page.get_by_role('button', name='Review ingredient use', exact=True).click()
    expect(page.get_by_text('Recipe amount: 6 kg', exact=True)).to_be_visible()
    expect(page.get_by_text('1% allowance: +0.06 kg', exact=True)).to_be_visible()
    expect(page.get_by_text('Total deduction: 6.06 kg', exact=True)).to_be_visible()
    screenshot(page, 'shiftly-production-review-phone.png')
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '20'
    page.get_by_role('button', name='Confirm production and deduct stock', exact=True).click()
    expect(page.get_by_role('heading', name='Flavors made', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Chocolate base', exact=True)).to_be_visible()
    expect(page.get_by_text('3 batches', exact=True)).to_be_visible()
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '13.94'


def test_rendered_unknown_stock_blocks_confirmation(page, native_inventory):
    url, i = native_inventory
    product = i.service.create_product(i.tokens['owner'], fields(i, name='Unknown cream', sku='CREAM-0', baseUnit='kg'))
    recipe(i, product, name='Uncounted flavor')
    page.goto(url + '/production/run')
    page.get_by_role('checkbox', name='Add Uncounted flavor', exact=True).click()
    page.get_by_role('button', name='Review ingredient use', exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='no longer active')).to_be_visible()
    expect(page.get_by_text('Current stock is unknown.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Confirm production and deduct stock', exact=True)).to_be_disabled()
    assert production(i).logs(i.tokens['owner'])['items'] == []


def test_lost_confirmation_response_restores_same_log_without_duplicate(page, native_inventory):
    url, i = native_inventory
    made = recipe(i, stocked_product(i), amount='1')
    page.goto(url + '/production/run')
    page.get_by_role('checkbox', name='Add Chocolate base', exact=True).click()
    page.get_by_role('button', name='Review ingredient use', exact=True).click()

    def lose_post(route):
        response = route.fetch()
        assert response.status == 200
        route.abort()

    def lose_recovery(route):
        route.abort()

    page.route('**/api/mobile/production/logs', lose_post, times=1)
    page.route('**/api/mobile/production/logs/*', lose_recovery)
    page.get_by_role('button', name='Confirm production and deduct stock', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Could not')
    assert len(production(i).logs(i.tokens['owner'])['items']) == 1
    page.evaluate('window.__workspaceTest.flush()')
    page.unroute('**/api/mobile/production/logs/*', lose_recovery)
    page.evaluate("history.replaceState(null, '', '/production/review')")
    page.reload()
    expect(page.get_by_role('heading', name='Flavors made', exact=True)).to_be_visible()
    logs = production(i).logs(i.tokens['owner'])['items']
    assert len(logs) == 1 and logs[0]['entries'][0]['revisionId'] == made['revisionId']
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '18.99'


@pytest.fixture(scope='session')
def production_layout_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp('production-layout-render') / 'app.js'
    result = subprocess.run([os.environ.get('NATIVE_TEST_NODE', 'node'), str(ROOT / 'apps/mobile/tests/rendered/build.mjs'), str(out), 'tests/rendered/accounts-entry.tsx'], cwd=ROOT / 'apps/mobile', capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return out.read_bytes()


@pytest.fixture
def native_production_layout(inventory, production_layout_bundle):
    i = inventory
    with i.connect() as db:
        db.execute("UPDATE account_store_memberships SET role='production',capabilities=ARRAY['production.view','production.submit'] WHERE user_id=%s", (i.users['crew'],))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def run(self):
            if self.path.startswith('/api/mobile/'):
                body = self.rfile.read(int(self.headers.get('Content-Length', '0')))
                response = i.client.request(self.command, self.path, headers=dict(self.headers), content=body)
                self.send_response(response.status_code); self.send_header('Content-Type', 'application/json'); self.end_headers(); self.wfile.write(response.content)
            elif self.path == '/app.js':
                self.send_response(200); self.send_header('Content-Type', 'text/javascript'); self.end_headers(); self.wfile.write(production_layout_bundle)
            else:
                html = '<meta name="viewport" content="width=device-width, initial-scale=1"><div id="root"></div>'
                html += '<script>window.__testToken=' + json.dumps(i.tokens['crew']) + '</script><script src="/app.js"></script>'
                self.send_response(200); self.send_header('Content-Type', 'text/html'); self.end_headers(); self.wfile.write(html.encode())
        do_GET = run
        do_POST = run
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler); thread = Thread(target=server.serve_forever, daemon=True); thread.start()
    yield f'http://127.0.0.1:{server.server_port}', i
    server.shutdown(); server.server_close(); thread.join(timeout=5)


def test_production_role_navigation_has_production_and_account_only(page, native_production_layout):
    url, i = native_production_layout
    i.client.app.state.context.services.stores.save_heads_up(i.stores[0], 'Prep freezer before opening.')
    page.goto(url + '/today')
    nav = page.get_by_role('navigation', name='Main navigation')
    for name in ('Today', 'Inventory', 'Production', 'Account'):
        expect(nav.get_by_role('button', name=name, exact=True)).to_be_visible()
    for name in ('Reports', 'Store'):
        expect(nav.get_by_role('button', name=name, exact=True)).to_have_count(0)
    expect(page.get_by_text('Prep freezer before opening.', exact=True)).to_be_visible()
    nav.get_by_role('button', name='Production', exact=True).click()
    expect(page.get_by_role('heading', name='Production', exact=True)).to_be_visible()


def test_recipe_modal_cancel_and_saved_recipe_edit(page, native_inventory):
    url, i = native_inventory
    made = recipe(i, stocked_product(i))
    page.goto(url + '/production/recipes/' + made['id'])
    expect(page.get_by_role('button', name='Edit Recipe', exact=True)).to_be_visible()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Edit Recipe', exact=True).click()
    # Earlier nonstandard yields must not silently become kilograms.
    expect(page.get_by_role('button', name='Save Recipe', exact=True)).to_be_disabled()
    page.get_by_label('Recipe name', exact=True).fill('Unsaved change')
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_value('Unsaved change')
    page.get_by_role('button', name='Recipe yield', exact=True).click()
    page.get_by_role('radio', name='4.5 kg', exact=True).click()
    page.get_by_role('button', name='Cancel', exact=True).click()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    original = production(i).recipe(i.tokens['owner'], made['id'])
    assert original['name'] == 'Chocolate base' and original['version'] == 1
    assert original['yieldAmount'] == '1' and original['yieldUnit'] == 'batch'

    page.get_by_role('button', name='Edit Recipe', exact=True).click()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_value('Chocolate base')
    page.get_by_role('button', name='Recipe yield', exact=True).click()
    page.get_by_role('radio', name='6 kg', exact=True).click()
    page.get_by_role('button', name='Save Recipe', exact=True).click()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    expect(page.get_by_text('Makes 6 kg', exact=True)).to_be_visible()
    assert production(i).recipe(i.tokens['owner'], made['id'])['version'] == 2
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '20'

    page.get_by_role('button', name='New Recipe', exact=True).click()
    page.get_by_label('Recipe name', exact=True).fill('Canceled flavor')
    page.get_by_role('button', name='Add Cocoa powder', exact=True).click()
    page.get_by_role('button', name='Cancel', exact=True).click()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    assert len(production(i).recipes(i.tokens['owner'])['items']) == 1
    page.get_by_role('button', name='New Recipe', exact=True).click()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_value('')
    expect(page.get_by_role('button', name='Remove Cocoa powder', exact=True)).to_have_count(0)


def test_recipe_modal_uncertain_save_cannot_be_canceled_or_duplicated(page, native_inventory):
    url, i = native_inventory
    stocked_product(i)
    page.goto(url + '/production/recipes/new')
    page.get_by_label('Recipe name', exact=True).fill('Recovered flavor')
    page.get_by_role('button', name='Add Cocoa powder', exact=True).click()
    submissions = []

    def intercept(route):
        if route.request.method != 'POST':
            route.continue_()
            return
        submissions.append(route.request.post_data_json)
        if len(submissions) == 1:
            assert route.fetch().status == 200
            route.abort()
        else:
            route.continue_()

    page.route('**/api/mobile/production/recipes', intercept)
    page.get_by_role('button', name='Save Recipe', exact=True).click()
    expect(page.get_by_role('button', name='Retry unchanged recipe save', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Cancel', exact=True)).to_be_disabled()
    expect(page.get_by_label('Recipe name', exact=True)).not_to_be_editable()
    expect(page.get_by_role('button', name='Recipe yield', exact=True)).to_be_disabled()
    page.keyboard.press('Escape')
    expect(page.get_by_label('Recipe name', exact=True)).to_be_visible()
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    page.get_by_role('button', name='Retry unchanged recipe save', exact=True).click()
    expect(page.get_by_role('button', name='Edit Recipe', exact=True)).to_be_visible()
    assert len(submissions) == 2 and submissions[0] == submissions[1]
    saved = production(i).recipes(i.tokens['owner'])['items']
    assert len(saved) == 1 and saved[0]['name'] == 'Recovered flavor'
    assert saved[0]['yieldAmount'] == '4.5' and saved[0]['yieldUnit'] == 'kg'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '20'
