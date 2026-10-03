"""Catalog measurement sheets preserve identity and require explicit recipe correction."""
from decimal import Decimal

from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields, start
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory


def cream(i):
    return i.service.create_product(i.tokens['owner'], fields(
        i, name='Heavy Cream', sku='070852990316', barcodeType='upc_a', baseUnit='each', containerAmount='1'))


def test_catalog_change_sheet_preserves_card_search_and_requires_new_recipe_amount(page, native_inventory):
    url, i = native_inventory
    item = cream(i)
    production = i.client.app.state.context.services.production
    recipe = production.create_recipe(i.tokens['owner'], fields(i, name='Stracciatella', yieldAmount='6', yieldUnit='kg',
        instructions='', ingredients=[{'productId': item['id'], 'amount': '1', 'unit': 'each'}]))
    page.goto(url + '/catalog')
    page.get_by_label('Find a product or SKU', exact=True).fill('Cream')
    page.get_by_role('button', name='Search catalog', exact=True).click()
    page.get_by_role('button', name='Change measurement: Heavy Cream', exact=True).click()
    expect(page.get_by_label('Full container amount (items)', exact=True)).to_have_value('1')
    page.get_by_role('radio', name='Kilograms', exact=True).click()
    expect(page.get_by_label('Full container amount (kg)', exact=True)).to_have_value('')
    page.get_by_label('Full container amount (kg)', exact=True).fill('2')
    page.get_by_role('button', name='Cancel', exact=True).click()
    assert i.service.product(i.tokens['owner'], item['id'])['baseUnit'] == 'each'
    expect(page.get_by_label('Find a product or SKU', exact=True)).to_have_value('Cream')
    page.get_by_role('button', name='Change measurement: Heavy Cream', exact=True).click()
    page.get_by_role('radio', name='Kilograms', exact=True).click()
    page.get_by_role('radio', name='lbs', exact=True).click()
    page.get_by_label('Full container amount (lbs)', exact=True).fill('2')
    expect(page.get_by_role('button', name='Save', exact=True)).to_be_disabled()
    page.get_by_role('checkbox', name='I’ll update the recipes using this item.', exact=True).click()
    for width, height in ((320, 900), (768, 900), (1024, 768), (1440, 900), (568, 320)):
        page.set_viewport_size({'width': width, 'height': height})
        page.wait_for_function('''() => {
            const action = document.querySelector('[aria-label="Save"]');
            if (!action) return false;
            const box = action.getBoundingClientRect();
            const key = [innerWidth, innerHeight, box.x, box.y, box.width, box.height].join(':');
            if (!window.__measurementLayout || window.__measurementLayout.key !== key) {
                window.__measurementLayout = { key, since: performance.now() };
                return false;
            }
            return performance.now() - window.__measurementLayout.since > 400
                && box.x >= 0 && box.right <= innerWidth && box.y >= 0 && box.bottom <= innerHeight;
        }''')
        expect(page.get_by_role('button', name='Save', exact=True)).to_be_visible()
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        page.screenshot(path=f'/private/tmp/shiftly-measurement-sheet-{width}.png', full_page=False, animations='disabled')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('button', name='Close measurement editor', exact=True)).to_have_count(0)
    expect(page.get_by_label('Find a product or SKU', exact=True)).to_have_value('Cream')
    changed = i.service.product(i.tokens['owner'], item['id'])
    assert changed['baseUnit'] == 'kg' and changed['containerAmount'] == '0.90718474'
    assert i.service.lookup_product(i.tokens['owner'], sku='070852990316', barcode_type='upc_a')['product']['id'] == item['id']
    page.goto(url + '/production/recipes/' + recipe['id'])
    page.get_by_role('button', name='Edit recipe', exact=True).click()
    expect(page.get_by_label('Amount', exact=True)).to_have_value('')
    expect(page.get_by_role('button', name='Save recipe', exact=True)).to_be_disabled()
    page.get_by_label('Amount', exact=True).fill('0.8')
    page.get_by_role('button', name='Save recipe', exact=True).click()
    expect(page.get_by_role('button', name='Close recipe editor', exact=True)).to_have_count(0)
    revised = production.recipe(i.tokens['owner'], recipe['id'])
    assert revised['ingredients'][0]['baseUnit'] == 'kg' and revised['ingredients'][0]['amount'] == '0.8'
    with i.connect() as c:
        assert c.execute('SELECT base_unit,base_amount FROM production_recipe_ingredients WHERE revision_id=%s',
                         (recipe['revisionId'],)).fetchone() == ('each', Decimal('1'))
        assert c.execute('SELECT count(*) FROM inventory_stock_balances').fetchone()[0] == 0


def test_measurement_stale_edit_preserves_draft_and_reload_recovers(page, native_inventory):
    url, i = native_inventory
    item = cream(i)
    page.goto(url + '/catalog/' + item['id'])
    expect(page.get_by_label('Full container amount (items)', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Change measurement: Heavy Cream', exact=True).click()
    page.get_by_role('radio', name='Kilograms', exact=True).click()
    page.get_by_label('Full container amount (kg)', exact=True).fill('1.2')
    i.service.edit_product(i.tokens['owner'], item['id'], fields(i, version=item['version'], name='Updated Cream', sku=item['sku']))
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('record changed')
    expect(page.get_by_label('Full container amount (kg)', exact=True)).to_have_value('1.2')
    expect(page.get_by_role('button', name='Save', exact=True)).to_be_disabled()
    page.get_by_role('button', name='Reload measurement', exact=True).click()
    expect(page.get_by_label('Full container amount (items)', exact=True)).to_have_value('1')
    page.get_by_role('radio', name='Kilograms', exact=True).click()
    page.get_by_label('Full container amount (kg)', exact=True).fill('1.2')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('button', name='Close measurement editor', exact=True)).to_have_count(0)
    saved = i.service.product(i.tokens['owner'], item['id'])
    assert saved['name'] == 'Updated Cream' and saved['baseUnit'] == 'kg'


def test_count_history_blocks_unit_change_but_allows_container_reference_edit(page, native_inventory):
    url, i = native_inventory
    item = i.service.create_product(i.tokens['owner'], fields(i, name='Sugar', sku='SUGAR', baseUnit='kg', containerAmount='6'))
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Dry goods'))
    i.service.place(i.tokens['owner'], shelf['id'], item['id'], fields(i, version=shelf['version'], active=True))
    counted = start(i)
    page.goto(url + '/catalog')
    page.get_by_role('button', name='Change measurement: Sugar', exact=True).click()
    page.get_by_role('radio', name='Each', exact=True).click()
    expect(page.get_by_role('alert')).to_contain_text('already included in an inventory count')
    expect(page.get_by_role('radio', name='Kilograms', exact=True)).to_have_attribute('aria-checked', 'true')
    page.get_by_label('Full container amount (kg)', exact=True).fill('8')
    page.get_by_role('button', name='Save', exact=True).click()
    expect(page.get_by_role('button', name='Close measurement editor', exact=True)).to_have_count(0)
    assert i.service.product(i.tokens['owner'], item['id'])['containerAmount'] == '8'
    with i.connect() as c:
        assert c.execute('SELECT base_unit,container_amount FROM inventory_count_products WHERE count_id=%s AND product_id=%s',
                         (counted['id'], item['id'])).fetchone() == ('kg', Decimal('6'))
    page.goto(url + '/catalog?crew')
    expect(page.get_by_role('button', name='View product: Sugar', exact=True)).to_be_visible()
    expect(page.get_by_role('button', name='Change measurement: Sugar', exact=True)).to_have_count(0)


def test_recipe_draft_from_before_measurement_correction_is_not_reinterpreted(page, native_inventory):
    url, i = native_inventory
    item = cream(i)
    production = i.client.app.state.context.services.production
    recipe = production.create_recipe(i.tokens['owner'], fields(i, name='Cream flavor', yieldAmount='6', yieldUnit='kg',
        instructions='', ingredients=[{'productId': item['id'], 'amount': '1', 'unit': 'each'}]))
    page.goto(url + '/production/recipes/' + recipe['id'])
    page.get_by_role('button', name='Edit recipe', exact=True).click()
    page.get_by_label('Amount', exact=True).fill('4')
    page.evaluate('window.__workspaceTest.flush()')
    i.service.correct_measurement(i.tokens['owner'], item['id'], fields(i, version=item['version'], baseUnit='kg',
        containerAmount='1.2', containerUnit='kg', acknowledgeRecipes=True))
    page.reload()
    expect(page.get_by_label('Amount', exact=True)).to_have_value('')
    expect(page.get_by_role('button', name='Use kg for Heavy Cream', exact=True)).to_have_attribute('aria-selected', 'true')
    expect(page.get_by_role('button', name='Save recipe', exact=True)).to_be_disabled()
    assert production.recipe(i.tokens['owner'], recipe['id'])['ingredients'][0]['amount'] == '1'
