"""Rendered counts cover every active catalog product, including no-shelf items."""
from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields, start
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_rendered_offline_counts import enter_total, place, product, shelf


def test_count_starts_with_active_catalog_and_no_shelf_filter_requires_explicit_zero(page, native_inventory):
    url, i = native_inventory
    first = product(i, 'Loose cocoa', 'LOOSE-COCOA')
    second = product(i, 'Loose sugar', 'LOOSE-SUGAR')
    archived = product(i, 'Archived salt', 'ARCHIVED-SALT')
    shelved = product(i, 'Shelved flour', 'SHELVED-FLOUR')
    location = shelf(i, 'Dry shelf')
    place(i, location['id'], shelved['id'])
    i.service.product_state(i.tokens['owner'], archived['id'], fields(
        i, version=archived['version'], active=False))

    page.goto(url + '/counts')
    page.get_by_role('button', name='Start store count', exact=True).click()
    expect(page.get_by_role('button', name='Count Loose cocoa · Unassigned', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Count Loose sugar · Unassigned', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Count Shelved flour · Dry shelf', exact=True)).to_be_visible()
    expect(page.get_by_text('Archived salt', exact=True)).to_have_count(0)

    page.get_by_role('button', name='Choose shelf: All shelves', exact=True).click()
    page.get_by_role('radio', name='No shelf assigned', exact=True).click()
    expect(page.get_by_role('button', name='Choose shelf: No shelf assigned', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Count Shelved flour · Dry shelf', exact=True)).to_have_count(0)
    expect(page.get_by_role('button', name='Search inventory', exact=True)).to_have_count(0)
    page.get_by_label('Find a product', exact=True).fill('Loose cocoa')
    expect(page.get_by_role('button', name='Count Loose cocoa · Unassigned', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Count Loose sugar · Unassigned', exact=True)).to_have_count(0)

    page.get_by_role('button', name='Count Loose cocoa · Unassigned', exact=True).click()
    save = page.get_by_role('button', name='Save', exact=True)
    expect(save).to_be_disabled()
    page.get_by_role('button', name='Set count to zero', exact=True).click()
    save.click()
    expect(page.get_by_test_id('count-entry-modal')).to_have_count(0)
    expect(page.get_by_role('button', name='All saved entries synced', exact=True)).to_be_visible()
    page.get_by_role('button', name='All', exact=True).click()
    saved_row = page.get_by_role(
        'button', name='Count Loose cocoa · Unassigned', exact=True)
    expect(saved_row.get_by_text('0 items', exact=True)).to_be_visible()

    count_id = i.counts.dashboard(i.tokens['owner'])['openCount']['id']
    lines = {line['productId']: line for line in i.counts.lines(i.tokens['owner'], count_id)['items']}
    assert lines[first['id']]['quantity'] == '0'
    assert lines[second['id']]['quantity'] is None
    assert archived['id'] not in lines


def test_reconnect_appends_new_catalog_product_without_losing_queued_entry(page, native_inventory):
    url, i = native_inventory
    original_product = product(i, 'Original cocoa', 'ORIGINAL-COCOA')
    count = start(i)
    original_line = i.counts.lines(i.tokens['owner'], count['id'])['items'][0]

    page.goto(url + f'/counts/{count["id"]}')
    expect(page.get_by_role('button', name='Count Original cocoa · Unassigned', exact=True)).to_be_visible()
    page.route('**/api/mobile/**', lambda route: route.abort())
    enter_total(page, 'Count Original cocoa · Unassigned', '5')
    expect(page.get_by_role('button', name='Counts waiting to sync', exact=True)).to_be_visible()

    added = product(i, 'Later sugar', 'LATER-SUGAR')
    changed = i.counts.detail(i.tokens['owner'], count['id'])
    assert changed['configurationChanged']
    assert changed['catalogProductsAvailable']

    page.reload()
    expect(page.get_by_role('button', name='Reconnect to Shiftly', exact=True)).to_be_visible()
    page.unroute('**/api/mobile/**')
    page.get_by_role('button', name='Reconnect to Shiftly', exact=True).click()
    expect(page.get_by_role('button', name='Back to count inventory', exact=True)).to_be_visible()
    page.get_by_role('button', name='Counts waiting to sync', exact=True).click()
    page.get_by_role('button', name='Sync now', exact=True).click()
    expect(page.get_by_text('Every saved entry has reached Shiftly.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Close saved counts', exact=True).click()

    expect(page.get_by_role('button', name='Count Later sugar · Unassigned', exact=True)).to_be_visible()
    page.get_by_role('button', name='All', exact=True).click()
    original_row = page.get_by_role(
        'button', name='Count Original cocoa · Unassigned', exact=True)
    expect(original_row.get_by_text('5 items', exact=True)).to_be_visible()

    lines = {line['productId']: line for line in i.counts.lines(i.tokens['owner'], count['id'])['items']}
    assert lines[original_product['id']]['id'] == original_line['id']
    assert lines[original_product['id']]['quantity'] == '5'
    assert lines[original_product['id']]['version'] == 2
    assert lines[added['id']]['quantity'] is None
    assert lines[added['id']]['version'] == 1
    assert not i.counts.detail(i.tokens['owner'], count['id'])['catalogProductsAvailable']
