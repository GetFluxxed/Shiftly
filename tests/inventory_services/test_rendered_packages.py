"""Rendered native package setup, barcode linking and mixed counting journeys."""
import os
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def shot(page, name):
    directory = os.environ.get('PACKAGE_SCREENSHOT_DIR')
    if directory:
        page.screenshot(path=str(Path(directory) / name), full_page=True)
    assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')


def product(i, name='Spoons', sku='SPOON-BOX'):
    item = i.service.create_product(i.tokens['owner'], fields(i, name=name, sku=sku, baseUnit='each', containerAmount='1000'))
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Back shelf'))
    i.service.place(i.tokens['owner'], shelf['id'], item['id'], fields(i, version=shelf['version'], active=True))
    return item


def test_rendered_package_case_and_mixed_count_are_exact(page, native_inventory):
    url, i = native_inventory; item = product(i)
    page.set_viewport_size({'width': 390, 'height': 844}); page.goto(url + f'/catalog/packages/{item["id"]}')
    expect(page.get_by_role('heading', name='Container', exact=True)).to_be_visible()
    page.get_by_role('button', name='New package', exact=True).click()
    page.get_by_label('Package name', exact=True).fill('Case of ten boxes')
    page.get_by_role('button', name='case', exact=False).click()
    page.get_by_role('button', name='Container', exact=True).click()
    page.get_by_label('Number of Container', exact=True).fill('10')
    page.get_by_label('Barcode (optional)', exact=True).fill('SPOON-CASE')
    for width in (320, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        shot(page, 'shiftly-packages-phone.png' if width == 320 else 'shiftly-packages-tablet.png' if width == 1024 else f'shiftly-packages-{width}.png')
    page.set_viewport_size({'width': 390, 'height': 844})
    page.get_by_role('button', name='Add package', exact=True).click()
    expect(page.get_by_role('heading', name='Case of ten boxes', exact=True)).to_be_visible()
    options = i.service.packages(i.tokens['owner'], item['id'])['items']; case = next(row for row in options if row['name'] == 'Case of ten boxes')
    assert case['amount'] == '10000' and case['barcodes'] == ['SPOON-CASE']

    page.goto(url + '/counts'); page.get_by_role('button', name='Start store count', exact=True).click()
    page.get_by_role('button', name='Count Spoons · Back shelf', exact=True).click()
    page.get_by_role('button', name='Add one Case of ten boxes', exact=True).click(); page.get_by_role('button', name='Add one Case of ten boxes', exact=True).click()
    for _ in range(3): page.get_by_role('button', name='Add one Container', exact=True).click()
    page.get_by_label('Loose items', exact=True).fill('250')
    expect(page.get_by_role('heading', name='This location: 23250 items', exact=True)).to_be_visible()
    shot(page, 'shiftly-mixed-count-phone.png')
    page.get_by_role('button', name='Save count entry', exact=True).click()
    page.get_by_role('button', name='Count Spoons · Back shelf', exact=True).click()
    expect(page.get_by_label('Case of ten boxes count', exact=True)).to_have_value('2')
    expect(page.get_by_label('Container count', exact=True)).to_have_value('3')
    expect(page.get_by_label('Loose items', exact=True)).to_have_value('250')
    page.get_by_role('button', name='Back to count entries', exact=True).first.click()


def test_rendered_unknown_barcode_links_package_to_chosen_existing_item(page, native_inventory):
    url, i = native_inventory; item = product(i, name='Rice', sku='RICE-BASE')
    page.goto(url + '/catalog/scan')
    page.get_by_label('Barcode or SKU', exact=True).fill('RICE-CASE-12')
    page.get_by_role('button', name='Look up code', exact=True).click()
    page.get_by_role('button', name='Add package to existing item', exact=True).click()
    page.get_by_role('button', name='Add package to Rice', exact=True).click()
    expect(page.get_by_label('Barcode (optional)', exact=True)).to_have_value('RICE-CASE-12')
    page.get_by_label('Package name', exact=True).fill('12 item case')
    page.evaluate('window.__workspaceTest.flush()')
    page.evaluate('window.__inventoryTest.lock()'); expect(page.get_by_text('Workspace locked', exact=True)).to_be_visible(); page.evaluate('window.__inventoryTest.retry()')
    expect(page.get_by_label('Package name', exact=True)).to_have_value('12 item case')
    expect(page.get_by_label('Barcode (optional)', exact=True)).to_have_value('RICE-CASE-12')
    page.goto(url)
    expect(page.get_by_label('Package name', exact=True)).to_have_value('12 item case')
    expect(page.get_by_label('Barcode (optional)', exact=True)).to_have_value('RICE-CASE-12')
    page.get_by_role('button', name='case', exact=False).click()
    page.get_by_label('Full amount (each)', exact=True).fill('12')
    page.get_by_role('button', name='Add package', exact=True).click()
    expect(page.get_by_role('heading', name='12 item case', exact=True)).to_be_visible()
    found = i.service.lookup_product(i.tokens['owner'], sku='RICE-CASE-12')
    assert found['product']['id'] == item['id'] and found['package']['name'] == '12 item case'
    page.get_by_role('button', name='Back to scanner', exact=True).click()
    expect(page.get_by_text('Rice is already in the catalog as 12 item case.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Back to scanner', exact=True).click()
    page.get_by_role('button', name='Back to catalog', exact=True).click()
    expect(page.get_by_role('button', name='Scan product', exact=True)).to_be_visible()
    page.evaluate('window.__workspaceTest.flush()')
    page.get_by_role('button', name='Scan product', exact=True).click()
    expect(page.get_by_role('heading', name='Scan your products.', exact=True)).to_be_visible()
    page.get_by_label('Barcode or SKU', exact=True).fill('RICE-CASE-24')
    page.get_by_role('button', name='Look up code', exact=True).click()
    page.get_by_role('button', name='Add package to existing item', exact=True).click()
    page.get_by_role('button', name='Add package to Rice', exact=True).click()
    expect(page.get_by_label('Barcode (optional)', exact=True)).to_have_value('RICE-CASE-24')
    expect(page.get_by_label('Package name', exact=True)).to_have_value('')


def test_rendered_package_stale_edit_restores_draft_and_is_rejected(page, native_inventory):
    url, i = native_inventory; item = product(i, name='Cocoa', sku='COCOA-BASE')
    option = i.service.packages(i.tokens['owner'], item['id'])['items'][0]
    page.goto(url + f'/catalog/packages/{item["id"]}')
    page.get_by_label('Edit Container', exact=True).click()
    page.get_by_label('Package name', exact=True).fill('My restored package draft')
    i.service.edit_package(i.tokens['owner'], item['id'], option['id'], fields(i, version=option['version'], name='Server package name', kind='container', amount=option['amount']))
    page.evaluate('window.__workspaceTest.flush()'); page.reload()
    expect(page.get_by_label('Package name', exact=True)).to_have_value('My restored package draft')
    page.get_by_role('button', name='Save package', exact=True).click()
    expect(page.get_by_role('alert')).to_be_visible()
    expect(page.get_by_label('Package name', exact=True)).to_have_value('My restored package draft')
    assert i.service.packages(i.tokens['owner'], item['id'])['items'][0]['name'] == 'Server package name'


def test_rendered_owner_reviews_and_combines_same_item_records(page, native_inventory):
    url, i = native_inventory
    source = product(i, name='Bacio 2.5 kg', sku='BACIO-25')
    target = i.service.create_product(i.tokens['owner'], fields(i, name='Bacio Base', sku='BACIO-BASE', baseUnit='each', containerAmount='1000'))
    page.goto(url)
    page.get_by_role('button', name='Open company catalog', exact=True).click()
    page.get_by_role('button', name='View product: Bacio 2.5 kg', exact=True).click()
    page.get_by_role('button', name='Manage packages & barcodes', exact=True).click()
    page.get_by_role('button', name='Use as a package of another item', exact=True).click()
    page.get_by_role('button', name='Review Bacio Base as the main item', exact=True).click()
    expect(page.get_by_text('Container · 1000 each', exact=True)).to_be_visible()
    page.get_by_role('button', name='Combine items', exact=True).click()
    expect(page.get_by_label('Product name', exact=True)).to_have_value('Bacio Base')
    linked = i.service.product(i.tokens['owner'], source['id'])
    assert linked['canonicalProductId'] == target['id'] and linked['active'] is False
    page.get_by_role('button', name='Back to catalog', exact=True).first.click()
    expect(page.get_by_role('button', name='View product: Bacio Base', exact=True)).to_be_visible()
