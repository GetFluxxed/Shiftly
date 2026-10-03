"""Compact shelf, stock table, and product-level count progress journeys."""
import os
from pathlib import Path
from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields, post, start
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


def no_clip(page, name):
    for width in (320, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        if directory := os.environ.get('COMPACT_INVENTORY_SCREENSHOT_DIR'):
            page.screenshot(path=str(Path(directory) / f'{name}-{width}.png'), full_page=True)


def test_assigned_products_lead_with_storewide_unknown_and_zero_then_stock_table(page, native_inventory):
    url, i = native_inventory
    location = shelf(i, 'Compact shelf')
    zero = product(i, 'Zero cocoa', 'ZERO-COCOA'); place(i, location['id'], zero['id'])
    count = start(i); line = i.counts.lines(i.tokens['owner'], count['id'])['items'][0]
    saved = i.counts.save(i.tokens['owner'], count['id'], line['id'], fields(
        i, version=line['version'], entry={'mode':'total', 'amount':'0', 'unit':'each'}))
    post(i, saved['count'])
    unknown = product(i, 'Unknown cocoa', 'UNKNOWN-COCOA'); place(i, location['id'], unknown['id'])

    page.goto(url + '/shelves/' + location['id'])
    expect(page.get_by_text('Storewide current inventory', exact=True)).to_have_count(2)
    expect(page.get_by_text('0 items', exact=True)).to_be_visible()
    expect(page.get_by_text('N/A', exact=True)).to_be_visible()
    content = page.locator('body').inner_text()
    assert content.index('Assigned products') < content.index('Find a product to assign')
    expect(page.get_by_label('Shelf name', exact=True)).to_have_count(0)
    no_clip(page, 'compact-shelf')

    page.goto(url + '/stock')
    for heading in ('Product', 'Quantity', 'Unit', 'Updated'):
        expect(page.get_by_text(heading, exact=True)).to_be_visible()
    zero_row = page.get_by_role('button', name='View stock: Zero cocoa. 0 items', exact=True)
    unknown_row = page.get_by_role('button', name='View stock: Unknown cocoa. N/A items', exact=True)
    expect(zero_row.get_by_text('0', exact=True)).to_be_visible()
    expect(unknown_row.get_by_text('N/A', exact=True)).to_be_visible()
    no_clip(page, 'compact-stock')
    zero_row.click(); expect(page.get_by_role('heading', name='Zero cocoa', exact=True)).to_be_visible()


def test_count_header_tracks_products_only_after_every_location_is_accounted_for(page, native_inventory):
    url, i = native_inventory
    item = product(i, 'Two shelf cocoa', 'TWO-SHELF')
    first, second = shelf(i, 'Shelf one'), shelf(i, 'Shelf two')
    place(i, first['id'], item['id']); place(i, second['id'], item['id'])
    page.goto(url + '/counts')
    page.get_by_role('button', name='Start store count', exact=True).click()
    expect(page.get_by_role('heading', name='Count', exact=True)).to_be_visible()
    expect(page.get_by_text('Product accounted for: 0/1', exact=True)).to_be_visible()
    page.get_by_role('button', name='Count Two shelf cocoa · Shelf one', exact=True).click()
    page.get_by_role('button', name='None remaining — save zero', exact=True).click()
    expect(page.get_by_text('Product accounted for: 0/1', exact=True)).to_be_visible()
    expect(page.get_by_text('1 of 2 required locations counted', exact=True)).to_be_visible()
    page.get_by_role('button', name='Count Two shelf cocoa · Shelf two', exact=True).click()
    page.get_by_role('button', name='None remaining — save zero', exact=True).click()
    expect(page.get_by_text('Product accounted for: 1/1', exact=True)).to_be_visible()
    expect(page.get_by_text('2 of 2 required locations counted', exact=True)).to_be_visible()
    no_clip(page, 'compact-count')


def test_stock_table_keeps_large_and_tiny_exact_quantities_readable_at_320(page, native_inventory):
    url, i = native_inventory
    location = shelf(i, 'Precision shelf')
    large = i.service.create_product(i.tokens['owner'], fields(i, name='Large exact', sku='LARGE-EXACT', baseUnit='kg', containerAmount='1'))
    tiny = i.service.create_product(i.tokens['owner'], fields(i, name='Tiny exact', sku='TINY-EXACT', baseUnit='kg', containerAmount='1'))
    place(i, location['id'], large['id']); place(i, location['id'], tiny['id'])
    count = start(i)
    saved = None
    for line in i.counts.lines(i.tokens['owner'], count['id'])['items']:
        amount, unit = ('123456.789', 'kg') if line['productId'] == large['id'] else ('0.000001', 'g')
        saved = i.counts.save(i.tokens['owner'], count['id'], line['id'], fields(
            i, version=line['version'], entry={'mode':'total', 'amount':amount, 'unit':unit}))
    post(i, saved['count'])
    page.set_viewport_size({'width':320, 'height':900}); page.goto(url + '/stock')
    large_row = page.get_by_role('button', name='View stock: Large exact. 123456.789 kg', exact=True)
    tiny_row = page.get_by_role('button', name='View stock: Tiny exact. 0.000000001 kg', exact=True)
    expect(large_row.get_by_text('123456.789', exact=True)).to_be_visible()
    expect(tiny_row.get_by_text('0.000000001', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
