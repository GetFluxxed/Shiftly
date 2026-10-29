"""Rendered native count durability, offline reload, sync, and conflict recovery."""
from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields, start
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def product(i, name, sku):
    return i.service.create_product(i.tokens['owner'], fields(
        i, name=name, sku=sku, baseUnit='each', containerAmount='12'))


def shelf(i, name):
    return i.service.create_shelf(i.tokens['owner'], fields(i, name=name))


def place(i, shelf_id, product_id):
    current = i.service.shelf(i.tokens['owner'], shelf_id)
    i.service.place(i.tokens['owner'], shelf_id, product_id, fields(
        i, version=current['version'], active=True))


def enter_total(page, row_label, amount):
    page.get_by_role('button', name=row_label, exact=True).click()
    page.get_by_role('radio', name='Measured total', exact=True).click()
    page.get_by_role('textbox', name='Measured total', exact=True).fill(amount)
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_test_id('count-entry-modal')).to_have_count(0)


def test_two_offline_entries_survive_reload_and_sync_exactly(page, native_inventory):
    url, i = native_inventory
    first = product(i, 'Offline cocoa', 'OFFLINE-COCOA')
    second = product(i, 'Offline sugar', 'OFFLINE-SUGAR')
    location = shelf(i, 'Offline shelf')
    place(i, location['id'], first['id']); place(i, location['id'], second['id'])
    count = start(i)

    page.goto(url + f'/counts/{count["id"]}')
    expect(page.get_by_role('button', name='Count Offline cocoa · Offline shelf', exact=True)).to_be_visible()
    page.route('**/api/mobile/**', lambda route: route.abort())

    enter_total(page, 'Count Offline cocoa · Offline shelf', '4')
    enter_total(page, 'Count Offline sugar · Offline shelf', '7')
    expect(page.get_by_role('button', name='Counts waiting to sync', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Review count', exact=True)).to_be_disabled()

    page.reload()
    expect(page.get_by_role('button', name='Reconnect to Shiftly', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Review count', exact=True)).to_be_disabled()
    page.get_by_role('button', name='All', exact=True).click()
    expect(page.get_by_role('button', name='Count Offline cocoa · Offline shelf', exact=True).get_by_text('4 items', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Count Offline sugar · Offline shelf', exact=True).get_by_text('7 items', exact=True)).to_be_visible()

    page.unroute('**/api/mobile/**')
    page.get_by_role('button', name='Reconnect to Shiftly', exact=True).click()
    expect(page.get_by_role('button', name='Back to count inventory', exact=True)).to_be_visible()
    page.get_by_role('button', name='Counts waiting to sync', exact=True).click()
    page.get_by_role('button', name='Sync now', exact=True).click()
    expect(page.get_by_text('Every saved entry has reached Shiftly.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Close saved counts', exact=True).click()
    expect(page.get_by_role('button', name='All saved entries synced', exact=True)).to_be_visible()

    saved = {line['productId']: line for line in i.counts.lines(i.tokens['owner'], count['id'])['items']}
    assert saved[first['id']]['quantity'] == '4'
    assert saved[second['id']]['quantity'] == '7'
    assert saved[first['id']]['version'] == 2
    assert saved[second['id']]['version'] == 2


def test_offline_conflict_keeps_local_quantity_until_explicit_resolution(page, native_inventory):
    url, i = native_inventory
    item = product(i, 'Conflict cocoa', 'CONFLICT-COCOA')
    location = shelf(i, 'Conflict shelf'); place(i, location['id'], item['id'])
    count = start(i)
    original = i.counts.lines(i.tokens['owner'], count['id'])['items'][0]

    page.goto(url + f'/counts/{count["id"]}')
    expect(page.get_by_role('button', name='Count Conflict cocoa · Conflict shelf', exact=True)).to_be_visible()
    page.route('**/api/mobile/**', lambda route: route.abort())
    enter_total(page, 'Count Conflict cocoa · Conflict shelf', '5')

    i.counts.save(i.tokens['owner'], count['id'], original['id'], fields(
        i, version=original['version'], entry={'mode': 'total', 'amount': '9', 'unit': 'each'}))
    page.get_by_role('button', name='All', exact=True).click()
    expect(page.get_by_role('button', name='Count Conflict cocoa · Conflict shelf', exact=True).get_by_text('5 items', exact=True)).to_be_visible()

    page.unroute('**/api/mobile/**')
    page.get_by_role('button', name='Reconnect to Shiftly', exact=True).click()
    page.get_by_role('button', name='Saved counts need attention', exact=True).click()
    expect(page.get_by_text('Your count: 5 items', exact=True)).to_be_visible()
    page.once('dialog', lambda dialog: dialog.accept())
    page.get_by_role('button', name='Keep my count', exact=True).click()
    expect(page.get_by_role('button', name='Close saved counts', exact=True)).to_be_visible()
    page.get_by_role('button', name='Close saved counts', exact=True).click()
    page.get_by_role('button', name='Counts waiting to sync', exact=True).click()
    page.get_by_role('button', name='Sync now', exact=True).click()
    expect(page.get_by_text('Every saved entry has reached Shiftly.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Close saved counts', exact=True).click()
    expect(page.get_by_role('button', name='All saved entries synced', exact=True)).to_be_visible()

    saved = i.counts.line(i.tokens['owner'], count['id'], original['id'])
    assert saved['quantity'] == '5'
    assert saved['version'] == 3


def test_pending_old_count_blocks_new_count_review_and_returns_to_queued_count(page, native_inventory):
    url, i = native_inventory
    item = product(i, 'Queued cocoa', 'QUEUED-COCOA')
    location = shelf(i, 'Queued shelf'); place(i, location['id'], item['id'])
    old = start(i)

    page.goto(url + f'/counts/{old["id"]}')
    expect(page.get_by_role('button', name='Count Queued cocoa · Queued shelf', exact=True)).to_be_visible()
    page.route('**/api/mobile/**', lambda route: route.abort())
    enter_total(page, 'Count Queued cocoa · Queued shelf', '5')
    expect(page.get_by_role('button', name='Counts waiting to sync', exact=True)).to_be_visible()

    cancelled = i.counts.transition(i.tokens['owner'], old['id'], 'cancel', fields(i, version=old['version']))
    assert cancelled['state'] == 'cancelled'
    new = start(i)

    page.unroute('**/api/mobile/**')
    page.get_by_role('button', name='Reconnect to Shiftly', exact=True).click()
    expect(page.get_by_role('button', name='Counts waiting to sync', exact=True)).to_be_visible()
    page.goto(url + f'/counts/{new["id"]}/review')
    expect(page.get_by_text('Sync or resolve your saved entries before reviewing this count.', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Submit for review', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Finalize inventory count', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Return to count', exact=True).click()

    page.get_by_role('button', name='All', exact=True).click()
    expect(page.get_by_role('button', name='Count Queued cocoa · Queued shelf', exact=True).get_by_text('5 items', exact=True)).to_be_visible()
