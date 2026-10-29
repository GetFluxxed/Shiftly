"""Rendered recipe-only ingredients remain descriptive and never deduct stock."""
from playwright.sync_api import expect

from tests.inventory_services.test_rendered_native import inventory_bundle, native_inventory
from tests.inventory_services.test_rendered_production import production, stocked_product


def add_reference(page, index, name, amount, unit):
    page.get_by_role('button', name='Recipe-only ingredient', exact=True).click()
    page.get_by_label(f'Recipe-only ingredient name {index}', exact=True).fill(name)
    page.get_by_label(f'Recipe-only amount {index}', exact=True).fill(amount)
    page.get_by_role('button', name=f'Use {unit} for recipe-only {name}', exact=True).click()


def test_mixed_recipe_only_ingredients_save_edit_cancel_and_do_not_deduct_stock(page, native_inventory):
    url, i = native_inventory
    stocked_product(i, amount='20')

    page.goto(url + '/production/recipes/new')
    page.get_by_label('Recipe name', exact=True).fill('First fruit recipe')
    page.get_by_role('button', name='Add Cocoa powder', exact=True).click()
    add_reference(page, 1, 'Water', '2', 'kg')
    add_reference(page, 2, 'Fresh strawberries', '12', 'each')
    expect(page.get_by_text('Shown in recipe; no stock deduction.', exact=True)).to_be_visible()
    page.get_by_role('button', name='Save recipe', exact=True).click()

    expect(page.get_by_role('button', name='Edit recipe', exact=True)).to_be_visible()
    expect(page.get_by_text('Recipe only', exact=True)).to_have_count(2)
    expect(page.get_by_text('2 kg', exact=True)).to_be_visible()
    expect(page.get_by_text('12 each', exact=True)).to_be_visible()
    saved = production(i).recipes(i.tokens['owner'])['items'][0]
    assert saved['referenceIngredients'] == [
        {'name': 'Water', 'amount': '2', 'unit': 'kg'},
        {'name': 'Fresh strawberries', 'amount': '12', 'unit': 'each'},
    ]

    page.get_by_role('button', name='Edit recipe', exact=True).click()
    water = page.get_by_label('Recipe-only amount 2', exact=True)
    if page.get_by_label('Recipe-only ingredient name 1', exact=True).input_value() == 'Water':
        water = page.get_by_label('Recipe-only amount 1', exact=True)
    water.fill('3')
    page.get_by_role('button', name='Cancel', exact=True).click()
    assert production(i).recipe(i.tokens['owner'], saved['id'])['referenceIngredients'] == saved['referenceIngredients']

    page.get_by_role('button', name='Edit recipe', exact=True).click()
    names = [page.get_by_label(f'Recipe-only ingredient name {index}', exact=True).input_value() for index in (1, 2)]
    assert sorted(names) == ['Fresh strawberries', 'Water']
    page.get_by_role('button', name='Save recipe', exact=True).click()
    expect(page.get_by_text('Recipe only', exact=True)).to_have_count(2)

    page.goto(url + '/production/run')
    page.get_by_role('checkbox', name='Add First fruit recipe', exact=True).click()
    page.get_by_role('button', name='Review ingredient use', exact=True).click()
    expect(page.get_by_text('Water', exact=True)).to_have_count(0)
    expect(page.get_by_text('Fresh strawberries', exact=True)).to_have_count(0)
    page.get_by_role('button', name='Confirm production and deduct stock', exact=True).click()
    expect(page.get_by_role('heading', name='Flavors made', exact=True)).to_be_visible()
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '18.99'
