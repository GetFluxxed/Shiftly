"""Real catalog screens/services; manual code entry is the camera fallback.

These journeys do not claim a physical iPhone camera has been exercised.
"""
import os
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def open_scanner(page, url, code):
    page.goto(url)
    page.get_by_role('button', name='Open company catalog', exact=True).click()
    page.get_by_role('button', name='Scan product', exact=True).click()
    page.get_by_label('Barcode or SKU', exact=True).fill(code)
    page.get_by_role('button', name='Look up code', exact=True).click()


def create_product(i, code, name='Existing ingredient'):
    return i.service.create_product(i.tokens['owner'], {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
        'name': name, 'sku': code, 'baseUnit': 'kg', 'containerAmount': '6',
    })


def test_scan_draft_restores_then_creates_once_without_stock(page, native_inventory):
    url, i = native_inventory
    page.set_viewport_size({'width': 390, 'height': 844})
    open_scanner(page, url, '000SCAN-06')
    expect(page.get_by_label('SKU', exact=True)).to_have_value('000SCAN-06')
    expect(page.get_by_label('SKU', exact=True)).not_to_be_editable()
    page.get_by_label('Product name', exact=True).fill('White Quella')
    page.get_by_role('button', name='Kilograms', exact=True).click()
    page.get_by_label('Full container amount (kg)', exact=True).fill('6')
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 0
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    expect(page.get_by_label('Product name', exact=True)).to_have_value('White Quella')
    expect(page.get_by_label('Full container amount (kg)', exact=True)).to_have_value('6')
    for width in (320, 390, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if directory := os.environ.get('INVENTORY_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(directory) / f'scan-new-{width}.png'), full_page=True)
    page.get_by_role('button', name='Create product', exact=True).click()
    expect(page.get_by_text('White Quella was added to the catalog.', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='White Quella', exact=True)).to_be_visible()
    page.get_by_role('button', name='Enter another code', exact=True).click()
    page.get_by_label('Barcode or SKU', exact=True).fill('000SCAN-06')
    page.get_by_role('button', name='Look up code', exact=True).click()
    expect(page.get_by_text('White Quella is already in the catalog.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    with i.connect() as c:
        assert c.execute('SELECT sku,name,base_unit,container_amount FROM inventory_products').fetchall() == [('000SCAN-06', 'White Quella', 'kg', 6)]
        for table in ('inventory_stock_balances', 'inventory_stock_movements', 'inventory_store_products', 'inventory_shelf_products'):
            assert c.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_scan_old_alias_opens_archived_product_without_recreating(page, native_inventory):
    url, i = native_inventory
    p = create_product(i, '000OLD')
    p = i.service.edit_product(i.tokens['owner'], p['id'], {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
        'name': p['name'], 'sku': '000NEW', 'version': p['version'],
    })
    i.service.product_state(i.tokens['owner'], p['id'], {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], 'active': False, 'version': p['version'],
    })
    open_scanner(page, url, '000OLD')
    expect(page.get_by_text('Existing ingredient is already in the catalog, but archived. Open it to review or restore it.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    page.get_by_role('button', name='View product', exact=True).click()
    expect(page.get_by_label('SKU', exact=True)).to_have_value('000NEW')
    expect(page.get_by_role('button', name='Restore product', exact=True)).to_be_visible()


def test_scan_lookup_failure_does_not_offer_creation(page, native_inventory):
    url, _ = native_inventory
    page.route('**/api/mobile/inventory/products/lookup?*', lambda route: route.fulfill(status=503, json={'error': 'Lookup unavailable.'}))
    open_scanner(page, url, '000RETRY')
    expect(page.get_by_role('alert').filter(has_text='Lookup unavailable.')).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    page.unroute('**/api/mobile/inventory/products/lookup?*')
    page.get_by_role('button', name='Reload', exact=True).click()
    expect(page.get_by_label('SKU', exact=True)).to_have_value('000RETRY')


def test_scan_creation_race_opens_existing_product(page, native_inventory):
    url, i = native_inventory
    open_scanner(page, url, '000RACE')
    page.get_by_label('Product name', exact=True).fill('My pending name')
    created = create_product(i, '000RACE', 'Added by another person')
    page.get_by_role('button', name='Create product', exact=True).click()
    expect(page.get_by_text('Added by another person is already in the catalog.', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name=created['name'], exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 1


def test_scan_crew_can_find_but_cannot_create_products(page, native_inventory):
    url, i = native_inventory
    p = create_product(i, '000VIEW')
    open_scanner(page, url + '?crew', p['sku'])
    expect(page.get_by_role('heading', name=p['name'], exact=True)).to_be_visible()
    page.get_by_role('button', name='Enter another code', exact=True).click()
    page.get_by_label('Barcode or SKU', exact=True).fill('000UNKNOWN')
    page.get_by_role('button', name='Look up code', exact=True).click()
    expect(page.get_by_role('heading', name='Product not found', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    expect(page.get_by_label('Product name', exact=True)).to_have_count(0)


def test_rejected_code_can_be_edited_or_rescanned_without_stock_changes(page, native_inventory):
    url, i = native_inventory
    page.route('**/api/mobile/inventory/products/lookup?*', lambda route: route.fulfill(
        status=400, json={'error': 'Choose a supported barcode type.'}))
    open_scanner(page, url, '6749118517')
    expect(page.get_by_text('Scanned code: 6749118517', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Change code', exact=True).click()
    expect(page.get_by_label('Barcode or SKU', exact=True)).to_have_value('6749118517')
    page.get_by_role('button', name='Look up code', exact=True).click()
    page.get_by_role('button', name='Scan again', exact=True).click()
    expect(page.get_by_role('heading', name='Barcode camera', exact=True)).to_be_visible()
    page.get_by_role('button', name='Enter code instead', exact=True).click()
    expect(page.get_by_label('Barcode or SKU', exact=True)).to_have_value('')
    with i.connect() as connection:
        for table in ('inventory_products', 'inventory_stock_balances', 'inventory_stock_movements'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
