"""Native camera events through real catalog UI/API; no physical camera claim."""
import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
from playwright.sync_api import expect
from tests.inventory_services.test_rendered_native import native_inventory

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope='session')
def inventory_bundle(tmp_path_factory):
    out = tmp_path_factory.mktemp('native-catalog-camera') / 'app.js'
    result = subprocess.run([
        os.environ.get('NATIVE_TEST_NODE', 'node'),
        str(ROOT / 'apps/mobile/tests/rendered/build.mjs'), str(out),
        'tests/rendered/entry.tsx', '--native-barcode',
    ], cwd=ROOT / 'apps/mobile', capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stderr
    return out.read_bytes()


def start_camera(page, url):
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url)
    page.get_by_role('button', name='Open company catalog', exact=True).click()
    page.get_by_role('button', name='Scan product', exact=True).click()
    page.evaluate('window.__catalogCameraTest.allow()')
    page.get_by_role('button', name='Open camera', exact=True).click()


def scan(page, code, kind):
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.evaluate('window.__catalogCameraTest.ready()')
    page.evaluate('([code,kind]) => { window.__catalogCameraTest.scan(code,kind); window.__catalogCameraTest.staleScan(code,kind); }', [code, kind])


def test_saved_milk_repeat_native_scans_show_name_without_creation(page, native_inventory):
    url, i = native_inventory
    start_camera(page, url)
    scan(page, '6749118517', 'org.iso.Code39')
    page.get_by_role('button', name='Create new item', exact=True).click()
    expect(page.get_by_label('SKU', exact=True)).to_have_value('6749118517')
    page.get_by_label('Product name', exact=True).fill('Low-Heat Non-Fat Dry Milk')
    page.get_by_role('button', name='Create product', exact=True).click()
    expect(page.get_by_text('Low-Heat Non-Fat Dry Milk was added to the catalog.', exact=True)).to_be_visible()
    for kind in ('code39', 'org.iso.Code39'):
        page.get_by_role('button', name='Scan next product', exact=True).click()
        scan(page, '6749118517', kind)
        expect(page.get_by_text('Low-Heat Non-Fat Dry Milk is already in the catalog as Container.', exact=True)).to_be_visible()
        expect(page.get_by_label('Product name', exact=True)).to_have_count(0)
        expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    if directory := os.environ.get('INVENTORY_SCREENSHOT_DIR'):
        page.screenshot(path=str(Path(directory) / 'repeat-milk-scan.png'), full_page=True)
    with i.connect() as connection:
        assert connection.execute('SELECT name,sku FROM inventory_products').fetchall() == [('Low-Heat Non-Fat Dry Milk', '6749118517')]
        for table in ('inventory_store_products', 'inventory_shelf_products', 'inventory_stock_balances', 'inventory_stock_movements'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0
    page.get_by_role('button', name='View product', exact=True).click()
    expect(page.get_by_label('Product name', exact=True)).to_have_value('Low-Heat Non-Fat Dry Milk')


def test_existing_padded_gtin_matches_short_native_scan_without_new_product(page, native_inventory):
    url, i = native_inventory
    product = i.service.create_product(i.tokens['owner'], {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
        'name': 'Filberts Chopped', 'sku': '00072488009455', 'baseUnit': 'kg',
    })
    start_camera(page, url)
    scan(page, '072488009455', 'ean13')
    expect(page.get_by_text('Filberts Chopped is already in the catalog.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    page.get_by_role('button', name='View product', exact=True).click()
    expect(page.get_by_label('SKU', exact=True)).to_have_value('00072488009455')
    with i.connect() as connection:
        assert connection.execute('SELECT id::text FROM inventory_products').fetchall() == [(product['id'],)]


def test_camera_header_back_returns_to_code_entry_before_catalog(page, native_inventory):
    url, _ = native_inventory
    start_camera(page, url)
    expect(page.get_by_label('Barcode camera preview')).to_be_visible()
    page.get_by_role('button', name='Back to scanner', exact=True).click()
    expect(page.get_by_label('Barcode or SKU', exact=True)).to_be_visible()
    expect(page.get_by_label('Barcode camera preview')).to_have_count(0)
    page.get_by_role('button', name='Back to catalog', exact=True).click()
    expect(page.get_by_role('button', name='Scan product', exact=True)).to_be_visible()
