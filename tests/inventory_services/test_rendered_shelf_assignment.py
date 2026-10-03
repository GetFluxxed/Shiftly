"""Shelf assignment stays mounted while authoritative updates complete."""
import os
import re
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def fields(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def setup_shelf(i, count=3):
    products = [i.service.create_product(i.tokens['owner'], fields(
        i, name=f'Ingredient {n:02}', sku=f'PRIVATE-SKU-{n:02}', baseUnit='kg', containerAmount='6',
    )) for n in range(count)]
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Ingredients shelf'))
    return shelf, products


def remember_picker(page):
    page.evaluate('''() => {
      window.__pickerNode = document.querySelector('[data-testid="shelf-product-picker"]');
      window.__pickerLost = false;
      new MutationObserver(() => {
        if (!window.__pickerNode.isConnected) window.__pickerLost = true;
      }).observe(document.body, {childList: true, subtree: true});
    }''')


def test_shelf_add_remove_keeps_picker_search_and_page(page, native_inventory):
    url, i = native_inventory
    shelf, products = setup_shelf(i, 42)
    page.add_init_script("""(() => {
      const fetch = window.fetch.bind(window);
      window.fetch = async (input, options) => {
        const response = await fetch(input, options);
        if (new URL(input).pathname === window.__holdShelfPath && options?.method === 'GET') {
          window.__holdShelfPath = null;
          return new Promise(resolve => {
            window.__releaseShelfRead = () => resolve(response);
          });
        }
        return response;
      };
    })()""")
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url + '/shelves/' + shelf['id'])
    query = page.get_by_label('Find a product to assign', exact=True)
    expect(query).to_be_visible()
    expect(page.get_by_label('Shelf name', exact=True)).to_have_count(0)
    query.fill('Ingredient')
    page.get_by_role('button', name='Find products', exact=True).click()
    page.get_by_role('button', name='Next page', exact=True).click()
    target = page.get_by_role('button', name='Assign Ingredient 40', exact=True)
    expect(target).to_be_visible()
    target.scroll_into_view_if_needed()
    remember_picker(page)
    before_y = query.bounding_box()['y']
    page.evaluate('path => { window.__holdShelfPath = path; }', '/api/mobile/inventory/shelves/' + shelf['id'])
    target.click()
    page.wait_for_function('typeof window.__releaseShelfRead === \"function\"')
    expect(query).to_have_value('Ingredient')
    expect(page.get_by_label('Shelf name', exact=True)).to_have_count(0)
    expect(page.get_by_text('Loading shelf…', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Assign Ingredient 41', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Back to first page', exact=True)).to_be_disabled()
    assert page.evaluate('window.__pickerNode.isConnected && !window.__pickerLost')
    assert abs(query.bounding_box()['y'] - before_y) <= 2
    page.evaluate('window.__releaseShelfRead()')
    expect(page.get_by_role('button', name='Ingredient 40 is assigned', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Assign Ingredient 41', exact=True)).to_be_enabled()
    assert abs(query.bounding_box()['y'] - before_y) <= 2
    page.get_by_role('button', name='Assign Ingredient 41', exact=True).click()
    expect(page.get_by_role('button', name='Ingredient 41 is assigned', exact=True)).to_be_visible()
    page.get_by_role('button', name='Remove Ingredient 40 from shelf', exact=True).click()
    expect(page.get_by_role('button', name='Assign Ingredient 40', exact=True)).to_be_enabled()
    expect(page.get_by_role('button', name='Remove Ingredient 40 from shelf', exact=True)).to_have_count(0)
    expect(query).to_have_value('Ingredient')
    expect(page.get_by_label('Shelf name', exact=True)).to_have_count(0)
    assert page.evaluate('window.__pickerNode.isConnected && !window.__pickerLost')
    assert [p['id'] for p in i.service.shelf(i.tokens['owner'], shelf['id'])['products']['items']] == [products[41]['id']]
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_stock_balances').fetchone()[0] == 0


def test_shelf_failed_write_keeps_context_and_failed_refresh_hides_stale_data(page, native_inventory):
    url, i = native_inventory
    shelf, products = setup_shelf(i)
    page.goto(url + '/shelves/' + shelf['id'])
    query = page.get_by_label('Find a product to assign', exact=True)
    expect(query).to_be_visible()
    query.fill('Ingredient')
    page.get_by_role('button', name='Find products', exact=True).click()
    remember_picker(page)
    endpoint = url + '/api/mobile/inventory/shelves/' + shelf['id']
    write = endpoint + '/products/' + products[0]['id']
    page.route(write, lambda route: route.fulfill(status=409, json={
        'error': 'This shelf changed. Reload before trying again.', 'errorCode': 'stale_record',
    }), times=1)
    page.get_by_role('button', name='Assign Ingredient 00', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('This shelf changed')
    expect(query).to_have_value('Ingredient')
    expect(page.get_by_role('button', name='Assign Ingredient 00', exact=True)).to_be_enabled()
    assert page.evaluate('window.__pickerNode.isConnected && !window.__pickerLost')
    assert not i.service.shelf(i.tokens['owner'], shelf['id'])['products']['items']
    page.route(re.compile(re.escape(endpoint) + r'(?:\?.*)?$'), lambda route: route.fulfill(status=503, json={'error': 'Shelf read unavailable.'}), times=1)
    page.get_by_role('button', name='Assign Ingredient 00', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('Shelf read unavailable.')
    expect(page.get_by_role('button', name='Assign Ingredient 01', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Reload', exact=True).click()
    expect(page.get_by_role('button', name='Ingredient 00 is assigned', exact=True)).to_be_visible()
    expect(query).to_have_value('Ingredient')
    page.evaluate('window.__inventoryTest.lock()')
    expect(page.get_by_test_id('shelf-product-picker')).to_have_count(0)


def test_compact_shelf_picker_name_size_only_with_accessible_rows(page, native_inventory):
    url, i = native_inventory
    shelf, _ = setup_shelf(i, 0)
    names = ('Almond paste with a deliberately long supplier description', 'Gloves', 'Mirtillo')
    for name, amount, unit in zip(names, ('6', '100', None), ('kg', 'each', 'kg')):
        i.service.create_product(i.tokens['owner'], fields(i, name=name, sku=str(uuid4()), baseUnit=unit, containerAmount=amount))
    page.goto(url + '/shelves/' + shelf['id'])
    picker = page.get_by_test_id('shelf-product-picker')
    expect(picker.get_by_text('6 kg', exact=True)).to_be_visible()
    expect(picker.get_by_text('100 items', exact=True)).to_be_visible()
    expect(picker.get_by_text('Size not set', exact=True)).to_be_visible()
    assert 'SKU' not in picker.inner_text() and 'Full container:' not in picker.inner_text()
    errors = []
    page.on('pageerror', lambda error: errors.append(str(error)))
    for width in (320, 390, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        picker.scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        for name in names:
            button = picker.get_by_role('button', name='Assign ' + name, exact=True)
            bounds = button.bounding_box()
            assert bounds['height'] >= 48 and bounds['width'] >= 48
        if directory := os.environ.get('INVENTORY_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(directory) / f'shelf-picker-{width}.png'), full_page=True)
    query = page.get_by_label('Find a product to assign', exact=True)
    query.focus()
    page.keyboard.press('Tab')
    expect(page.get_by_role('button', name='Find products', exact=True)).to_be_focused()
    page.keyboard.press('Tab')
    expect(picker.get_by_role('button', name='Assign ' + names[0], exact=True)).to_be_focused()
    page.keyboard.press('Enter')
    expect(picker.get_by_role('button', name=names[0] + ' is assigned', exact=True)).to_be_visible()
    assert not errors


def test_newer_server_placement_wins_over_local_add_confirmation(page, native_inventory):
    url, i = native_inventory
    shelf, products = setup_shelf(i, 1)
    page.goto(url + '/shelves/' + shelf['id'])
    assign = page.get_by_role('button', name='Assign Ingredient 00', exact=True)
    expect(assign).to_be_visible()
    endpoint = url + '/api/mobile/inventory/shelves/' + shelf['id'] + '/products/' + products[0]['id']

    def change_before_refresh(route):
        response = route.fetch()
        saved = response.json()['shelf']
        i.service.place(i.tokens['owner'], shelf['id'], products[0]['id'], fields(
            i, version=saved['version'], active=False,
        ))
        route.fulfill(response=response)

    page.route(endpoint, change_before_refresh, times=1)
    with page.expect_response(lambda response: response.url == endpoint):
        assign.click()
    expect(assign).to_be_enabled()
    expect(page.get_by_role('button', name='Ingredient 00 is assigned', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Remove Ingredient 00 from shelf', exact=True)).to_have_count(0)
    assert not i.service.shelf(i.tokens['owner'], shelf['id'])['products']['items']


def test_shelf_name_window_keeps_draft_on_conflict_and_respects_viewer_access(page, native_inventory):
    url, i = native_inventory
    shelf, products = setup_shelf(i, 1)
    i.service.place(i.tokens['owner'], shelf['id'], products[0]['id'], fields(i, version=shelf['version'], active=True))
    page.goto(url + '/shelves')
    edit = page.get_by_role('button', name='Edit shelf name: Ingredients shelf', exact=True)
    expect(edit).to_be_visible()
    bounds = edit.bounding_box()
    assert bounds['width'] >= 44 and bounds['height'] >= 44
    edit.click()
    expect(page.get_by_role('heading', name='Edit shelf name', exact=True)).to_be_visible()
    name = page.get_by_label('Shelf name', exact=True)
    expect(name).to_have_value('Ingredients shelf')
    expect(page.get_by_role('button', name='Save', exact=True)).to_be_disabled()
    name.fill('   ')
    expect(page.get_by_role('button', name='Save', exact=True)).to_be_disabled()
    name.fill('Back ingredients')
    for width, height in ((320, 760), (768, 360), (768, 760), (1024, 760), (1440, 760)):
        page.set_viewport_size({'width': width, 'height': height})
        expect(name).to_be_visible()
        expect(page.get_by_role('button', name='Save', exact=True)).to_be_in_viewport(ratio=1)
        expect(page.get_by_role('button', name='Cancel', exact=True)).to_be_in_viewport(ratio=1)
        expect(page.get_by_role('button', name='Save', exact=True)).to_be_visible()
        expect(page.get_by_role('button', name='Cancel', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if directory := os.environ.get('INVENTORY_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(directory) / f'shelf-name-{width}.png'), full_page=True)
    current = i.service.shelf(i.tokens['owner'], shelf['id'])
    i.service.edit_shelf(i.tokens['owner'], shelf['id'], fields(i, version=current['version'], name='Another editor'))
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('record changed')
    expect(name).to_have_value('Back ingredients')
    page.get_by_role('button', name='Reload shelf', exact=True).click()
    expect(name).to_have_value('Back ingredients')
    expect(page.get_by_role('button', name='Save', exact=True)).to_be_enabled()
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('button', name='Open Back ingredients', exact=True)).to_be_visible()
    expect(page.get_by_label('Shelf name', exact=True)).to_have_count(0)
    saved = i.service.shelf(i.tokens['owner'], shelf['id'])
    assert saved['name'] == 'Back ingredients'
    assert [item['id'] for item in saved['products']['items']] == [products[0]['id']]
    page.get_by_role('button', name='Open Back ingredients', exact=True).click()
    expect(page.get_by_role('heading', name='Assigned products', exact=True)).to_be_visible()
    expect(page.get_by_label('Shelf name', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Cancel', exact=True)).to_have_count(0)
    page.goto(url + '/shelves?crew')
    expect(page.get_by_role('button', name='Open Back ingredients', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Edit shelf name:', exact=False)).to_have_count(0)
