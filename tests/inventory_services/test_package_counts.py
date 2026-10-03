"""Mixed packaging is observation evidence; stock still belongs to the ingredient."""
from decimal import Decimal
from uuid import uuid4

import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.counts.validation import measurement
from backend.shiftly.production.service import ProductionService


def fields(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def prepare(i, *, unit='each', amount='1000', amount_unit=None):
    size = {'containerAmount': amount}
    if amount_unit is not None:
        size['containerUnit'] = amount_unit
    item = i.service.create_product(i.tokens['owner'], fields(i, name='Spoons' if unit == 'each' else 'Bacio Base',
        sku='BASE-1', baseUnit=unit, **size))
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Back shelf'))
    i.service.place(i.tokens['owner'], shelf['id'], item['id'], fields(i, version=shelf['version'], active=True))
    return item, i.service.packages(i.tokens['owner'], item['id'])['items'][0]


def start(i):
    count = i.counts.start(i.tokens['owner'], fields(i, businessDate='2026-10-01'))
    return count, i.counts.lines(i.tokens['owner'], count['id'])['items'][0]


def entry(*pairs, partial='0', unit='each'):
    return {'mode': 'packages', 'packages': [{'packageId': item['id'], 'count': quantity} for item, quantity in pairs],
            'partialAmount': partial, 'partialUnit': unit}


def save(i, count, line, value):
    return i.counts.save(i.tokens['owner'], count['id'], line['id'], fields(i, version=line['version'], entry=value))


def post(i, count):
    review = i.counts.transition(i.tokens['owner'], count['id'], 'review', fields(i, version=count['version']))
    return i.counts.transition(i.tokens['owner'], count['id'], 'post', fields(i, version=review['version']))


def test_case_box_and_partial_share_one_balance_and_keep_evidence(inventory):
    i = inventory
    product, box = prepare(i)
    case = i.service.create_package(i.tokens['owner'], product['id'], fields(i, name='Case of ten boxes', kind='case',
        containedPackageId=box['id'], containedCount=10, barcode='SPOON-CASE'))
    count, line = start(i)
    assert line['quantity'] is None and len(line['packages']) == 2
    result = save(i, count, line, entry((case, 2), (box, 3), partial='250'))
    assert result['line']['quantity'] == '23250'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None
    posted = post(i, result['count'])
    detail = i.counts.stock_detail(i.tokens['owner'], product['id'])
    assert detail['quantity'] == '23250'
    assert detail['locations']['items'][0]['entry'] == result['line']['entry']
    assert detail['locations']['items'][0]['packages'] == line['packages']
    assert posted['state'] == 'posted'
    assert i.service.lookup_product(i.tokens['owner'], sku='SPOON-CASE')['product']['id'] == product['id']


def test_opening_a_case_changes_packaging_not_total(inventory):
    i = inventory
    product, box = prepare(i)
    case = i.service.create_package(i.tokens['owner'], product['id'], fields(i, name='Case', kind='case',
        containedPackageId=box['id'], containedCount=10))
    first, line = start(i)
    post(i, save(i, first, line, entry((case, 1)))['count'])
    second, line = start(i)
    saved = save(i, second, line, entry((box, 9), partial='1000'))
    comparison = i.counts.comparisons(i.tokens['owner'], second['id'])['items'][0]
    assert comparison['quantity'] == '10000' and comparison['difference'] == '0'
    post(i, saved['count'])
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '10000'


def test_mixed_bacio_weights_feed_recipe_plus_one_percent_and_preserve_snapshot(inventory):
    i = inventory
    product, standard = prepare(i, unit='kg', amount='2')
    large = i.service.create_package(i.tokens['owner'], product['id'], fields(i, name='Bacio 50 MB', kind='container', amount='2.5', barcode='BACIO-50'))
    count, line = start(i)
    posted = post(i, save(i, count, line, entry((standard, 1), (large, 1), partial='250', unit='g'))['count'])
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '4.75'
    production = ProductionService(i.connect, i.accounts)
    recipe = production.create_recipe(i.tokens['owner'], fields(i, name='Base recipe', yieldAmount='4.5', yieldUnit='kg', instructions='',
        ingredients=[{'productId': product['id'], 'amount': '1', 'unit': 'kg'}]))
    production.confirm(i.tokens['owner'], fields(i, logId=str(uuid4()), confirmed=True, businessDate='2026-10-01',
        entries=[{'recipeId': recipe['id'], 'revisionId': recipe['revisionId'], 'batches': 1}]))
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '3.74'
    i.service.edit_package(i.tokens['owner'], product['id'], large['id'], fields(i, version=large['version'], name='Revised package', kind='container', amount='3'))
    history_line = i.counts.line(i.tokens['owner'], posted['id'], line['id'])
    old = next(p for p in history_line['packages'] if p['id'] == large['id'])
    assert old['amount'] == '2.5' and old['name'] == 'Bacio 50 MB'
    assert history_line['quantity'] == '4.75'


def test_pound_labeled_full_package_posts_metric_stock_and_snapshot_stays_immutable(inventory):
    i = inventory
    product, default = prepare(i, unit='kg', amount='50', amount_unit='lb')
    count, line = start(i)
    snap = next(p for p in line['packages'] if p['id'] == default['id'])
    assert (snap['amount'], snap['labelAmount'], snap['labelUnit']) == ('22.6796185', '50', 'lb')
    posted = post(i, save(i, count, line, entry((default, 1), partial='1000', unit='g'))['count'])
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] == '23.6796185'
    i.service.edit_package(i.tokens['owner'], product['id'], default['id'], fields(
        i, version=default['version'], name=default['name'], kind=default['kind'],
        amount=default['amount'], amountUnit='kg'))
    historical = i.counts.line(i.tokens['owner'], posted['id'], line['id'])
    old = next(p for p in historical['packages'] if p['id'] == default['id'])
    assert (old['labelAmount'], old['labelUnit']) == ('50', 'lb')


def test_package_edit_invalidates_open_count_and_missing_is_not_zero(inventory):
    i = inventory
    product, default = prepare(i)
    count, line = start(i)
    with pytest.raises(IdentityError, match='Count every location'):
        i.counts.transition(i.tokens['owner'], count['id'], 'review', fields(i, version=count['version']))
    saved = save(i, count, line, entry())
    assert saved['line']['quantity'] == '0'
    i.service.create_package(i.tokens['owner'], product['id'], fields(i, name='Small box', kind='box', amount='100'))
    with pytest.raises(IdentityError, match='changed during this count'):
        post(i, saved['count'])
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None


@pytest.mark.parametrize('value', [
    {'mode': 'packages', 'packages': [{'packageId': 'box', 'count': True}], 'partialAmount': '0', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [{'packageId': 'box', 'count': 1.5}], 'partialAmount': '0', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [{'packageId': 'box', 'count': -1}], 'partialAmount': '0', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [{'packageId': 'box', 'count': 1_000_001}], 'partialAmount': '0', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [{'packageId': 'foreign', 'count': 1}], 'partialAmount': '0', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [{'packageId': 'box', 'count': 1}] * 2, 'partialAmount': '0', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [], 'partialAmount': '0.5', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [], 'partialAmount': '10', 'partialUnit': 'kg'},
    {'mode': 'packages', 'packages': [], 'partialAmount': '-1', 'partialUnit': 'each'},
    {'mode': 'packages', 'packages': [], 'partialAmount': '0', 'partialUnit': 'each', 'amount': '100'},
])
def test_package_measurements_reject_ambiguous_or_invalid_observations(value):
    with pytest.raises(IdentityError):
        measurement(value, {'base_unit': 'each', 'packages': [{'id': 'box', 'amount': '1000', 'active': True}]})


def test_package_partial_conversion_is_exact_and_legacy_measurements_remain_readable():
    quantity, _ = measurement({'mode': 'packages', 'packages': [{'packageId': 'bag', 'count': 3}],
        'partialAmount': '0.000001', 'partialUnit': 'g'}, {'base_unit': 'kg', 'packages': [{'id': 'bag', 'amount': '2.5', 'active': True}]})
    assert quantity == Decimal('7.500000001')
    quantity, _ = measurement({'mode': 'containers', 'fullContainers': 2, 'partialAmount': '1250', 'partialUnit': 'g'},
        {'base_unit': 'kg', 'container_amount': Decimal('6'), 'packages': []})
    assert quantity == Decimal('13.25')
