"""Saved catalog capture journeys through the real native controller and storage."""
from playwright.sync_api import expect
from uuid import uuid4

from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_counts import start
from tests.inventory_services.test_rendered_offline_counts import place, product, shelf


def empty_catalog(i):
    with i.connect() as connection:
        assert connection.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 0


def test_saved_scan_persists_before_metadata_and_survives_failed_update_and_reload(page, native_inventory):
    url, i = native_inventory
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url + '/catalog/saved-scans')
    expect(page.get_by_role('heading', name='Saved scans', exact=True)).to_be_visible()
    page.get_by_label('Barcode or SKU', exact=True).fill('000042')
    page.get_by_role('button', name='Save code', exact=True).click()
    expect(page.get_by_text('Code saved on this device. Add details now, or save and keep scanning.', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Inbox (1/100)', exact=True)).to_be_visible()
    empty_catalog(i)

    page.get_by_label('Product name', exact=True).fill('Offline cocoa')
    page.get_by_role('button', name='Kilograms', exact=True).click()
    page.get_by_label('Full container amount (kg)', exact=True).fill('6')
    page.evaluate('window.__savedScansTest.failNextWrite()')
    page.get_by_role('button', name='Save optional details', exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='Saved scans could not be stored.')).to_be_visible()
    expect(page.get_by_label('Product name', exact=True)).to_have_value('Offline cocoa')
    expect(page.get_by_label('Full container amount (kg)', exact=True)).to_have_value('6')
    page.get_by_role('button', name='Retry saved scans', exact=True).click()
    expect(page.get_by_role('button', name='Retry saved scans', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Save optional details', exact=True).click()
    expect(page.get_by_text('Saved scan details updated.', exact=True)).to_be_visible()
    empty_catalog(i)

    page.reload()
    expect(page.get_by_role('heading', name='Offline cocoa', exact=True)).to_be_visible()
    expect(page.get_by_text('Code 000042', exact=True)).to_be_visible()
    expect(page.get_by_text('6 kg per container · count in kg', exact=True)).to_be_visible()
    empty_catalog(i)

    i.service.create_product(i.tokens['owner'], {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
        'name': 'Verified cocoa', 'sku': '000042', 'baseUnit': 'kg', 'containerAmount': '6',
    })
    page.get_by_role('button', name='Review saved scan: Offline cocoa', exact=True).click()
    expect(page.get_by_text('Verified cocoa is already in the catalog as Container.', exact=True)).to_be_visible()
    page.evaluate('window.__savedScansTest.failNextWrite()')
    page.get_by_role('button', name='Done with saved scan', exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='The completed scan could not be removed.')).to_be_visible()
    expect(page.get_by_role('heading', name='Verified cocoa', exact=True)).to_be_visible()
    page.get_by_role('button', name='Done with saved scan', exact=True).click()
    expect(page.get_by_role('heading', name='Inbox (0/100)', exact=True)).to_be_visible()


def test_lookup_failure_can_save_code_but_never_opens_creation_or_writes_catalog(page, native_inventory):
    url, i = native_inventory
    page.route('**/api/mobile/inventory/products/lookup?*', lambda route: route.fulfill(
        status=503, json={'error': 'Lookup unavailable.'}))
    page.goto(url + '/catalog/scan')
    page.get_by_label('Barcode or SKU', exact=True).fill('000RETRY')
    page.get_by_role('button', name='Look up code', exact=True).click()
    expect(page.get_by_role('alert').filter(has_text='Lookup unavailable.')).to_be_visible()
    expect(page.get_by_role('button', name='Create product', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Save code for later', exact=True).click()
    expect(page.get_by_text('Code saved on this device for later review.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Already in saved scans', exact=True)).to_be_disabled()
    empty_catalog(i)


def test_cold_offline_capture_persists_without_catalog_writes_then_reconnects_for_fresh_review(page, native_inventory):
    url, i = native_inventory
    page.goto(url + '/catalog/saved-scans')
    expect(page.get_by_text('Ready for offline scanning.', exact=True)).to_be_visible()
    page.wait_for_function("JSON.parse(localStorage.getItem('test.offline-permit') || 'null')?.catalogCapture === true")
    page.evaluate('window.__workspaceTest.flush()')
    page.evaluate('window.__savedScansTest.delayNextReadAfterReload(350)')
    page.route('**/api/mobile/**', lambda route: route.abort())
    page.reload()
    expect(page.get_by_text('Opening saved scans…', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Save code', exact=True)).to_be_disabled()
    expect(page.get_by_role('button', name='Reconnect', exact=True)).to_be_visible()

    page.get_by_label('Barcode or SKU', exact=True).fill('000OFFLINE')
    page.get_by_role('button', name='Save code', exact=True).click()
    page.get_by_label('Product name', exact=True).fill('Offline cocoa')
    page.get_by_role('button', name='Kilograms', exact=True).click()
    page.get_by_label('Full container amount (kg)', exact=True).fill('4')
    page.get_by_role('button', name='Save optional details', exact=True).click()
    expect(page.get_by_text('Saved scan details updated.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Cancel detail edits', exact=True).click()
    page.get_by_label('Barcode or SKU', exact=True).fill('000NEWOFF')
    page.get_by_role('button', name='Save code', exact=True).click()
    expect(page.get_by_role('heading', name='Inbox (2/100)', exact=True)).to_be_visible()
    empty_catalog(i)
    with i.connect() as connection:
        for table in ('inventory_stock_balances', 'inventory_stock_movements', 'inventory_store_products'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0

    page.reload()
    expect(page.get_by_role('heading', name='Offline cocoa', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='000NEWOFF', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Review saved scan: Offline cocoa', exact=True)).to_have_count(0)
    i.service.create_product(i.tokens['owner'], {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
        'name': 'Connected cocoa', 'sku': '000OFFLINE', 'baseUnit': 'kg', 'containerAmount': '4',
    })

    page.unroute('**/api/mobile/**')
    page.get_by_role('button', name='Reconnect', exact=True).click()
    expect(page.get_by_role('button', name='Review saved scan: Offline cocoa', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Review saved scan: 000NEWOFF', exact=True)).to_be_visible()
    page.get_by_role('button', name='Review saved scan: Offline cocoa', exact=True).click()
    expect(page.get_by_text('Connected cocoa is already in the catalog as Container.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Done with saved scan', exact=True).click()
    page.get_by_role('button', name='Review saved scan: 000NEWOFF', exact=True).click()
    expect(page.get_by_role('heading', name='Code not found', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Create new item', exact=True)).to_be_visible()
    with i.connect() as connection:
        assert connection.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 1
        for table in ('inventory_stock_balances', 'inventory_stock_movements', 'inventory_store_products'):
            assert connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] == 0


def test_failed_initial_inbox_read_blocks_capture_until_explicit_retry(page, native_inventory):
    url, _ = native_inventory
    page.goto(url + '/catalog/saved-scans')
    expect(page.get_by_text('Ready for offline scanning.', exact=True)).to_be_visible()
    page.wait_for_function("JSON.parse(localStorage.getItem('test.offline-permit') || 'null')?.catalogCapture === true")
    page.evaluate('window.__workspaceTest.flush()')
    page.evaluate('window.__savedScansTest.failReadsAfterReload()')
    page.reload()
    expect(page.get_by_role('alert').filter(has_text='Saved scans could not be restored.')).to_be_visible()
    page.get_by_label('Barcode or SKU', exact=True).fill('BLOCKED')
    expect(page.get_by_role('button', name='Save code', exact=True)).to_be_disabled()
    page.evaluate('window.__savedScansTest.clearReadFailure()')
    page.get_by_role('button', name='Retry saved scans', exact=True).click()
    expect(page.get_by_role('button', name='Retry saved scans', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Save code', exact=True).click()
    expect(page.get_by_role('heading', name='Inbox (1/100)', exact=True)).to_be_visible()


def test_dual_offline_grant_switches_between_count_and_saved_scans(page, native_inventory):
    url, i = native_inventory
    item = product(i, 'Dual offline cocoa', 'DUAL-OFFLINE')
    location = shelf(i, 'Dual offline shelf')
    place(i, location['id'], item['id'])
    count = start(i)
    page.goto(url + f'/counts/{count["id"]}')
    expect(page.get_by_role('button', name='Count Dual offline cocoa · Dual offline shelf', exact=True)).to_be_visible()

    page.goto(url + '/catalog/saved-scans')
    expect(page.get_by_text('Ready for offline scanning.', exact=True)).to_be_visible()
    page.wait_for_function("""(countId) => {
      const permit = JSON.parse(localStorage.getItem('test.offline-permit') || 'null');
      return permit?.catalogCapture === true && permit?.countId === countId;
    }""", arg=count['id'])
    page.evaluate('window.__workspaceTest.flush()')
    page.route('**/api/mobile/**', lambda route: route.abort())
    page.reload()
    expect(page.get_by_role('heading', name='Saved scans', exact=True)).to_be_visible()
    page.get_by_role('button', name='Back to count', exact=True).click()
    expect(page.get_by_role('heading', name='Count', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Saved scans', exact=True)).to_be_visible()
    page.get_by_role('button', name='Saved scans', exact=True).click()
    expect(page.get_by_role('heading', name='Saved scans', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Back to count', exact=True)).to_be_visible()
