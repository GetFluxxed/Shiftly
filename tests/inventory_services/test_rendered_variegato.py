"""Rendered recipes preserve distinct base and variegato ingredient rows."""
from playwright.sync_api import expect

from tests.inventory_services.test_counts import fields
from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_rendered_production import production, stocked_product


def card_for_remove(page, label):
    return page.get_by_role('button', name=label, exact=True).locator('..').locator('..')


def test_same_catalog_product_and_recipe_only_rows_preserve_variegato_section(page, native_inventory):
    url, i = native_inventory
    product = stocked_product(i, amount='20')

    page.goto(url + '/production/recipes/new')
    page.get_by_label('Recipe name', exact=True).fill('Cocoa variegato')
    page.get_by_role('button', name='Add Cocoa powder', exact=True).click()
    catalog_section = page.get_by_role('radiogroup', name='Catalog ingredient section', exact=True)
    catalog_section.get_by_role('radio', name='Variegato', exact=True).click()
    add_variegato = page.get_by_role('button', name='Add Cocoa powder to Variegato', exact=True)
    add_variegato.evaluate('(button) => { button.click(); button.click(); }')
    expect(page.get_by_role('button', name='Remove Cocoa powder from Variegato', exact=True)).to_have_count(1)

    base_card = card_for_remove(page, 'Remove Cocoa powder')
    variegato_card = card_for_remove(page, 'Remove Cocoa powder from Variegato')
    base_card.get_by_label('Amount', exact=True).fill('1')
    variegato_card.get_by_label('Amount', exact=True).fill('0.25')

    page.get_by_role('button', name='Recipe-only ingredient', exact=True).click()
    page.get_by_label('Recipe-only ingredient name 1', exact=True).fill('Raspberry ripple')
    page.get_by_label('Recipe-only amount 1', exact=True).fill('0.1')
    page.get_by_role('button', name='Use kg for recipe-only Raspberry ripple', exact=True).click()
    reference_section = page.get_by_role(
        'radiogroup', name='Section for recipe-only Raspberry ripple', exact=True)
    reference_section.get_by_role('radio', name='Variegato', exact=True).click()
    page.get_by_role('button', name='Save recipe', exact=True).click()

    expect(page.get_by_role('heading', name='Ingredients', exact=True)).to_be_visible()
    expect(page.get_by_role('heading', name='Variegato', exact=True)).to_be_visible()
    expect(page.get_by_text('Cocoa powder', exact=True)).to_have_count(2)
    expect(page.get_by_text('Raspberry ripple', exact=True)).to_be_visible()
    expect(page.get_by_text('Recipe only', exact=True)).to_be_visible()

    saved = production(i).recipes(i.tokens['owner'])['items'][0]
    cocoa_rows = [row for row in saved['ingredients'] if row['productId'] == product['id']]
    assert {(row.get('section', 'base'), row['amount']) for row in cocoa_rows} == {
        ('base', '1'), ('variegato', '0.25')}
    assert saved['referenceIngredients'] == [
        {'name': 'Raspberry ripple', 'amount': '0.1', 'unit': 'kg', 'section': 'variegato'}]

    page.get_by_role('button', name='Edit recipe', exact=True).click()
    page.get_by_role('button', name='Remove Cocoa powder from Variegato', exact=True).click()
    page.get_by_role('button', name='Cancel', exact=True).click()
    unchanged = production(i).recipe(i.tokens['owner'], saved['id'])
    assert len([row for row in unchanged['ingredients'] if row['productId'] == product['id']]) == 2

    page.get_by_role('button', name='Edit recipe', exact=True).click()
    expect(page.get_by_role('button', name='Remove Cocoa powder', exact=True)).to_be_visible()
    variegato_card = card_for_remove(page, 'Remove Cocoa powder from Variegato')
    variegato_card.get_by_label('Amount', exact=True).fill('0.5')
    page.get_by_role('button', name='Save recipe', exact=True).click()
    expect(page.get_by_label('Recipe name', exact=True)).to_have_count(0)
    revised = production(i).recipe(i.tokens['owner'], saved['id'])
    cocoa_rows = [row for row in revised['ingredients'] if row['productId'] == product['id']]
    assert {(row.get('section', 'base'), row['amount']) for row in cocoa_rows} == {
        ('base', '1'), ('variegato', '0.5')}
    assert revised['referenceIngredients'][0]['section'] == 'variegato'


def test_first_variegato_on_base_recipe_restores_and_retries_exact_sections(page, native_inventory):
    url, i = native_inventory
    product = stocked_product(i, amount='20')
    saved = production(i).create_recipe(i.tokens['owner'], fields(
        i, name='Base cocoa', yieldAmount='4.5', yieldUnit='kg', instructions='',
        ingredients=[{'productId': product['id'], 'amount': '1', 'unit': 'kg'}],
        referenceIngredients=[]))

    page.goto(url + '/production/recipes/' + saved['id'])
    page.get_by_role('button', name='Edit recipe', exact=True).click()
    catalog_section = page.get_by_role('radiogroup', name='Catalog ingredient section', exact=True)
    catalog_section.get_by_role('radio', name='Variegato', exact=True).click()
    page.get_by_role('button', name='Add Cocoa powder to Variegato', exact=True).click()
    card_for_remove(page, 'Remove Cocoa powder from Variegato').get_by_label(
        'Amount', exact=True).fill('0.375')
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()

    expect(page.get_by_role('button', name='Remove Cocoa powder from Variegato', exact=True)).to_be_visible()
    expect(card_for_remove(page, 'Remove Cocoa powder from Variegato').get_by_label(
        'Amount', exact=True)).to_have_value('0.375')
    submissions = []

    def intercept(route):
        if route.request.method != 'POST':
            route.continue_()
            return
        submissions.append(route.request.post_data_json)
        if len(submissions) == 1:
            route.abort()
        else:
            route.continue_()

    page.route('**/api/mobile/production/recipes/*', intercept)
    page.get_by_role('button', name='Save recipe', exact=True).click()
    expect(page.get_by_role('button', name='Retry unchanged recipe', exact=True)).to_be_visible()
    page.evaluate('window.__workspaceTest.flush()')
    page.reload()
    expect(page.get_by_role('button', name='Retry unchanged recipe', exact=True)).to_be_visible()
    expect(card_for_remove(page, 'Remove Cocoa powder from Variegato').get_by_label(
        'Amount', exact=True)).to_have_value('0.375')
    page.get_by_role('button', name='Retry unchanged recipe', exact=True).click()
    expect(page.get_by_role('button', name='Edit recipe', exact=True)).to_be_visible()
    assert len(submissions) == 2 and submissions[0] == submissions[1]
    assert {(row['section'], row['amount']) for row in submissions[0]['ingredients']} == {
        ('base', '1'), ('variegato', '0.375')}
