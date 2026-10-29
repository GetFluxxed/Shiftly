"""Pounds-labelled packages remain metric through native setup and posted counts."""
from decimal import Decimal

from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields
from tests.inventory_services.test_package_counts import post
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def test_rendered_barcode_free_pounds_product_keeps_label_and_posts_metric_stock(page, native_inventory, tmp_path):
    url, i = native_inventory
    page.set_viewport_size({'width': 390, 'height': 844})
    page.goto(url + '/catalog/new')
    page.get_by_label('Product name', exact=True).fill('Sugar')
    page.get_by_label('SKU', exact=True).fill('SUGAR-001')
    page.get_by_role('button', name='Pounds (lbs)', exact=True).click()
    page.get_by_label('Full container amount (lbs)', exact=True).fill('50')
    expect(page.get_by_text('One full container = 50 lbs = 22.6796185 kg. Inventory totals use kg.', exact=True)).to_be_visible()
    for width in (320, 768, 1024, 1440):
        page.set_viewport_size({'width': width, 'height': 900})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.set_viewport_size({'width': 320, 'height': 800})
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    expect(page.get_by_label('Full container amount (lbs)', exact=True)).to_have_value('50')
    page.screenshot(path=str(tmp_path / 'shiftly-pound-product-320.png'), full_page=True)
    page.get_by_role('button', name='Create product', exact=True).click()
    expect(page.get_by_role('button', name='Save company product', exact=True)).to_be_visible()
    expect(page.get_by_text('50 lbs (22.6796185 kg)', exact=True)).to_be_visible()
    product = i.service.products(i.tokens['owner'])['items'][0]
    assert product['baseUnit'] == 'kg' and product['containerAmount'] == '22.6796185'
    assert product['containerLabelAmount'] == '50' and product['containerLabelUnit'] == 'lb'
    page.get_by_label('Product name', exact=True).fill('Sugar bags')
    with page.expect_response(lambda response: response.request.method == 'POST' and response.url.endswith('/inventory/products/' + product['id'])):
        page.get_by_role('button', name='Save company product', exact=True).click()
    expect(page.get_by_text('50 lbs (22.6796185 kg)', exact=True)).to_be_visible()

    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Dry goods'))
    i.service.place(i.tokens['owner'], shelf['id'], product['id'], fields(i, version=shelf['version'], active=True))
    page.goto(url + '/counts')
    page.get_by_role('button', name='Start store count', exact=True).click()
    page.get_by_role('button', name='Count Sugar bags · Dry goods', exact=True).click()
    page.get_by_role('button', name='Add one Container', exact=True).click()
    page.get_by_role('button', name='Add one Container', exact=True).click()
    page.get_by_role('button', name='Grams', exact=True).click()
    page.get_by_label('Combined loose or partial amount', exact=True).fill('500')
    expect(page.get_by_role('heading', name='This location: 45.859237 kg', exact=True)).to_be_visible()
    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    page.screenshot(path=str(tmp_path / 'shiftly-pound-count-320.png'), full_page=True)
    page.get_by_role('button', name='Save count entry', exact=True).click()
    with i.connect() as c:
        count_id = str(c.execute('SELECT id FROM inventory_counts').fetchone()[0])
    count = i.counts.detail(i.tokens['owner'], count_id)
    post(i, count)
    stock = i.counts.stock_detail(i.tokens['owner'], product['id'])
    assert stock['quantity'] == '45.859237'
    assert stock['locations']['items'][0]['packages'][0]['labelUnit'] == 'lb'
    assert stock['locations']['items'][0]['packages'][0]['labelAmount'] == '50'
    with i.connect() as c:
        assert c.execute('SELECT quantity FROM inventory_stock_balances WHERE product_id=%s', (product['id'],)).fetchone()[0] == Decimal('45.859237')


def test_rendered_existing_metric_item_accepts_pound_package_and_restores_it(page, native_inventory):
    url, i = native_inventory
    product = i.service.create_product(i.tokens['owner'], fields(i, name='Dry Milk', sku='DRY-MILK', baseUnit='kg', containerAmount='6'))
    page.goto(url + f'/catalog/packages/{product["id"]}')
    page.get_by_role('button', name='New package', exact=True).click()
    page.get_by_label('Package name', exact=True).fill('50 lb bag')
    page.get_by_role('button', name='lbs', exact=True).click()
    page.get_by_label('Full amount (lbs)', exact=True).fill('50')
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    expect(page.get_by_label('Package name', exact=True)).to_have_value('50 lb bag')
    expect(page.get_by_label('Full amount (lbs)', exact=True)).to_have_value('50')
    page.get_by_role('button', name='Add package', exact=True).click()
    expect(page.get_by_role('heading', name='50 lb bag', exact=True)).to_be_visible()
    options = i.service.packages(i.tokens['owner'], product['id'])['items']
    bag = next(item for item in options if item['name'] == '50 lb bag')
    assert (bag['amount'], bag['labelAmount'], bag['labelUnit']) == ('22.6796185', '50', 'lb')
    assert i.service.product(i.tokens['owner'], product['id'])['containerAmount'] == '6'
    page.get_by_role('button', name='Edit 50 lb bag', exact=True).click()
    expect(page.get_by_label('Full amount (lbs)', exact=True)).to_have_value('50')
    page.get_by_label('Package name', exact=True).fill('Large milk bag')
    page.get_by_role('button', name='Save package', exact=True).click()
    expect(page.get_by_role('heading', name='Large milk bag', exact=True)).to_be_visible()
    changed = next(item for item in i.service.packages(i.tokens['owner'], product['id'])['items'] if item['id'] == bag['id'])
    assert (changed['amount'], changed['labelAmount'], changed['labelUnit']) == ('22.6796185', '50', 'lb')
