from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from threading import Event
from uuid import uuid4

import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production.service import ProductionService
from backend.shiftly.inventory import measurement_corrections
from test_storage import fields


def create(inventory, *, base_unit='kg', container_amount=None, sku=None):
    values = {
        'name': 'Measurement ingredient',
        'sku': sku or str(uuid4()),
        'baseUnit': base_unit,
    }
    if container_amount is not None:
        values['containerAmount'] = container_amount
    return inventory.service.create_product(inventory.tokens['owner'], fields(inventory, **values))


def correction(inventory, product, **values):
    return fields(inventory, **{
        'version': product['version'],
        'baseUnit': 'g',
        'containerAmount': None,
        'acknowledgeRecipes': False,
        **values,
    })


def assert_denied(code, operation):
    with pytest.raises(IdentityError) as caught:
        operation()
    assert caught.value.code == code
    return caught.value


def test_measurement_preview_requires_catalog_and_inventory_access_and_hides_foreign_products(inventory):
    item = create(inventory)
    expected = {
        'product': item,
        'canChangeUnit': True,
        'issues': [],
        'recipeCount': 0,
    }
    assert inventory.service.measurement_correction(inventory.tokens['owner'], item['id']) == expected
    assert inventory.service.measurement_correction(inventory.tokens['delegate'], item['id']) == expected
    assert_denied('forbidden', lambda: inventory.service.measurement_correction(inventory.tokens['crew'], item['id']))
    assert_denied('forbidden', lambda: inventory.service.measurement_correction(inventory.tokens['manager'], item['id']))
    assert_denied('not_found', lambda: inventory.service.measurement_correction(inventory.tokens['foreign'], item['id']))
    request = correction(inventory, item)
    assert_denied('forbidden', lambda: inventory.service.correct_measurement(
        inventory.tokens['crew'], item['id'], request))
    assert_denied('not_found', lambda: inventory.service.correct_measurement(
        inventory.tokens['foreign'], item['id'], {**request, 'expectedStoreId': inventory.stores[2]}))

    headers = {'Authorization': 'Bearer ' + inventory.tokens['owner']}
    response = inventory.client.get(f'/api/mobile/inventory/products/{item["id"]}/measurement', headers=headers)
    assert response.status_code == 200 and response.json() == expected
    posted = inventory.client.post(
        f'/api/mobile/inventory/products/{item["id"]}/measurement', headers=headers,
        json=request,
    )
    assert posted.status_code == 200 and posted.json()['baseUnit'] == 'g'


def test_measurement_post_rejects_a_stale_selected_store(inventory):
    item = create(inventory)
    headers = {'Authorization': 'Bearer ' + inventory.tokens['owner']}
    request = correction(inventory, item, expectedStoreId=inventory.stores[1])
    response = inventory.client.post(
        f'/api/mobile/inventory/products/{item["id"]}/measurement',
        headers=headers,
        json=request,
    )
    assert response.status_code == 409
    assert response.json()['errorCode'] == 'store_context_changed'
    assert inventory.service.product(inventory.tokens['owner'], item['id']) == item


def test_correction_is_versioned_idempotent_and_preserves_identity_aliases_and_shelves(inventory):
    item = create(inventory, sku='MEASURE-OLD')
    edited = inventory.service.edit_product(inventory.tokens['owner'], item['id'], fields(
        inventory, version=item['version'], name='Renamed ingredient', sku='MEASURE-NEW'))
    shelf = inventory.service.create_shelf(inventory.tokens['owner'], fields(inventory, name='Dry stock'))
    inventory.service.place(inventory.tokens['owner'], shelf['id'], item['id'], fields(
        inventory, version=shelf['version'], active=True))
    request = correction(inventory, edited, containerAmount='2', containerUnit='lb')

    changed = inventory.service.correct_measurement(inventory.tokens['owner'], item['id'], request)
    assert inventory.service.correct_measurement(inventory.tokens['owner'], item['id'], request) == changed
    assert changed == {
        **edited,
        'baseUnit': 'g',
        'containerAmount': '907.18474',
        'containerLabelAmount': '2',
        'containerLabelUnit': 'lb',
        'version': edited['version'] + 1,
    }
    package = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    assert package['amount'] == '907.18474' and package['labelAmount'] == '2' and package['labelUnit'] == 'lb'
    assert set(package['barcodes']) == {'MEASURE-OLD', 'MEASURE-NEW'}
    assert inventory.service.shelf(inventory.tokens['owner'], shelf['id'])['products']['items'][0]['id'] == item['id']

    with inventory.connect() as connection:
        assert connection.execute(
            'SELECT sku,package_id=%s FROM inventory_product_skus WHERE product_id=%s ORDER BY sku',
            (package['id'], item['id']),
        ).fetchall() == [('MEASURE-NEW', True), ('MEASURE-OLD', True)]
        assert connection.execute(
            "SELECT operation FROM inventory_changes WHERE target_id=%s ORDER BY id", (item['id'],)
        ).fetchall() == [('product.created',), ('product.edited',), ('product.measurement_corrected',)]
        assert connection.execute('SELECT count(*) FROM inventory_stock_balances').fetchone() == (0,)

    assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(inventory, edited)))


def test_correction_replay_rechecks_current_catalog_authority(inventory):
    item = create(inventory)
    request = correction(inventory, item)
    changed = inventory.service.correct_measurement(
        inventory.tokens['delegate'], item['id'], request)
    with inventory.connect() as connection:
        connection.execute(
            '''UPDATE account_store_memberships SET state='revoked'
               WHERE user_id=%s AND store_id=%s''',
            (inventory.users['delegate'], inventory.stores[0]),
        )
    denied = assert_denied('forbidden', lambda: inventory.service.correct_measurement(
        inventory.tokens['delegate'], item['id'], request))
    assert denied.reason == 'access_changed'
    assert inventory.service.product(inventory.tokens['owner'], item['id']) == changed


def test_correction_rejects_stale_unchanged_and_ambiguous_package_configuration(inventory):
    item = create(inventory, container_amount='6')
    stale = assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(inventory, item, version=99, containerAmount='6000')))
    assert stale.reason == 'stale_record'
    assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(
            inventory, item, baseUnit='kg', containerAmount='6')))
    assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(inventory, item)))

    inventory.service.create_package(inventory.tokens['owner'], item['id'], fields(
        inventory, name='Case', kind='case', containedPackageId=inventory.service.packages(
            inventory.tokens['owner'], item['id'])['items'][0]['id'], containedCount=2))
    preview = inventory.service.measurement_correction(inventory.tokens['owner'], item['id'])
    assert not preview['canChangeUnit']
    assert preview['issues'] == [measurement_corrections.PACKAGE_ISSUE]
    current = inventory.service.product(inventory.tokens['owner'], item['id'])
    assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(inventory, current, containerAmount='6000')))


def test_existing_default_package_is_updated_in_place(inventory):
    item = create(inventory, container_amount='6')
    before = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    changed = inventory.service.correct_measurement(inventory.tokens['owner'], item['id'], correction(
        inventory, item, containerAmount='6', containerUnit='kg'))
    after = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    assert changed['containerAmount'] == '6000' and changed['containerLabelUnit'] == 'kg'
    assert after['id'] == before['id'] and after['amount'] == '6000' and after['active']
    assert after['version'] == before['version'] + 1


def test_inactive_default_package_stays_inactive_and_keeps_legacy_mirror_clear(inventory):
    item = create(inventory, container_amount='6')
    default = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    archived = inventory.service.package_state(inventory.tokens['owner'], item['id'], default['id'], fields(
        inventory, version=default['version'], active=False))
    current = inventory.service.product(inventory.tokens['owner'], item['id'])

    changed = inventory.service.correct_measurement(inventory.tokens['owner'], item['id'], correction(
        inventory, current, containerAmount='6', containerUnit='kg'))
    package = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    assert changed['baseUnit'] == 'g'
    assert changed['containerAmount'] is None
    assert changed['containerLabelAmount'] is None and changed['containerLabelUnit'] is None
    assert package['id'] == archived['id'] and not package['active']
    assert package['amount'] == '6000' and package['labelAmount'] == '6' and package['labelUnit'] == 'kg'
    assert package['version'] == archived['version'] + 1


def test_all_inventory_and_production_evidence_is_reported_without_record_details(inventory):
    item = create(inventory)
    shelf = inventory.service.create_shelf(inventory.tokens['owner'], fields(inventory, name='Counted shelf'))
    inventory.service.place(inventory.tokens['owner'], shelf['id'], item['id'], fields(
        inventory, version=shelf['version'], active=True))
    count = inventory.counts.start(inventory.tokens['owner'], fields(inventory, businessDate='2026-10-02'))
    line = inventory.counts.lines(inventory.tokens['owner'], count['id'])['items'][0]
    saved = inventory.counts.save(inventory.tokens['owner'], count['id'], line['id'], fields(
        inventory, version=line['version'], entry={'mode': 'total', 'amount': '10', 'unit': 'kg'}))
    reviewed = inventory.counts.transition(inventory.tokens['owner'], count['id'], 'review', fields(
        inventory, version=saved['count']['version']))
    inventory.counts.transition(inventory.tokens['owner'], count['id'], 'post', fields(
        inventory, version=reviewed['version']))

    production = ProductionService(inventory.connect, inventory.accounts)
    recipe = production.create_recipe(inventory.tokens['owner'], fields(
        inventory, name='Private recipe name', yieldAmount='1', yieldUnit='batch', instructions='',
        ingredients=[{'productId': item['id'], 'amount': '1', 'unit': 'kg'}]))
    production.confirm(inventory.tokens['owner'], fields(
        inventory, logId=str(uuid4()), confirmed=True, businessDate='2026-10-02',
        entries=[{'recipeId': recipe['id'], 'revisionId': recipe['revisionId'], 'batches': 1}]))

    preview = inventory.service.measurement_correction(inventory.tokens['owner'], item['id'])
    assert not preview['canChangeUnit'] and preview['recipeCount'] == 1
    assert preview['issues'] == [message for _, message in measurement_corrections.HISTORY_CHECKS]
    assert 'Private recipe name' not in repr(preview)
    assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(
            inventory, item, containerAmount=None, acknowledgeRecipes=True)))


def test_recipe_acknowledgement_preserves_old_revision_and_allows_a_new_unit_revision(inventory):
    item = create(inventory)
    shelf = inventory.service.create_shelf(inventory.tokens['owner'], fields(inventory, name='Recipe shelf'))
    inventory.service.place(inventory.tokens['owner'], shelf['id'], item['id'], fields(
        inventory, version=shelf['version'], active=True))
    production = ProductionService(inventory.connect, inventory.accounts)
    recipe = production.create_recipe(inventory.tokens['owner'], fields(
        inventory, name='Dough', yieldAmount='1', yieldUnit='batch', instructions='',
        ingredients=[{'productId': item['id'], 'amount': '1', 'unit': 'kg'}]))

    preview = inventory.service.measurement_correction(inventory.tokens['owner'], item['id'])
    assert preview['canChangeUnit'] and preview['recipeCount'] == 1 and preview['issues'] == []
    assert_denied('conflict', lambda: inventory.service.correct_measurement(
        inventory.tokens['owner'], item['id'], correction(inventory, item)))
    changed = inventory.service.correct_measurement(inventory.tokens['owner'], item['id'], correction(
        inventory, item, acknowledgeRecipes=True))

    count = inventory.counts.start(inventory.tokens['owner'], fields(inventory, businessDate='2026-10-02'))
    line = inventory.counts.lines(inventory.tokens['owner'], count['id'])['items'][0]
    saved = inventory.counts.save(inventory.tokens['owner'], count['id'], line['id'], fields(
        inventory, version=line['version'], entry={'mode': 'total', 'amount': '10000', 'unit': 'g'}))
    reviewed = inventory.counts.transition(inventory.tokens['owner'], count['id'], 'review', fields(
        inventory, version=saved['count']['version']))
    inventory.counts.transition(inventory.tokens['owner'], count['id'], 'post', fields(
        inventory, version=reviewed['version']))
    old_preview = production.preview(inventory.tokens['owner'], {
        'businessDate': '2026-10-02',
        'entries': [{'recipeId': recipe['id'], 'revisionId': recipe['revisionId'], 'batches': 1}],
    })
    assert old_preview['issues'][0]['code'] == 'unit_changed'

    revised = production.edit_recipe(inventory.tokens['owner'], recipe['id'], fields(
        inventory, version=recipe['version'], name='Dough', yieldAmount='1', yieldUnit='batch', instructions='',
        ingredients=[{'productId': item['id'], 'amount': '1000', 'unit': 'g'}]))
    new_preview = production.preview(inventory.tokens['owner'], {
        'businessDate': '2026-10-02',
        'entries': [{'recipeId': revised['id'], 'revisionId': revised['revisionId'], 'batches': 1}],
    })
    assert new_preview['canConfirm']
    with inventory.connect() as connection:
        rows = connection.execute(
            '''SELECT revision_id,base_unit,base_amount FROM production_recipe_ingredients
               WHERE recipe_id=%s ORDER BY revision_id''', (recipe['id'],)
        ).fetchall()
        assert {str(row[0]): (row[1], row[2]) for row in rows} == {
            recipe['revisionId']: ('kg', Decimal('1')),
            revised['revisionId']: ('g', Decimal('1000')),
        }
    assert changed['baseUnit'] == 'g'


def test_only_current_recipe_revisions_are_counted(inventory):
    corrected = create(inventory, sku='OLD-RECIPE-INGREDIENT')
    replacement = create(inventory, sku='CURRENT-RECIPE-INGREDIENT')
    production = ProductionService(inventory.connect, inventory.accounts)
    recipe = production.create_recipe(inventory.tokens['owner'], fields(
        inventory, name='Revision count', yieldAmount='1', yieldUnit='batch', instructions='',
        ingredients=[{'productId': corrected['id'], 'amount': '1', 'unit': 'kg'}]))
    production.edit_recipe(inventory.tokens['owner'], recipe['id'], fields(
        inventory, version=recipe['version'], name='Revision count', yieldAmount='1', yieldUnit='batch', instructions='',
        ingredients=[{'productId': replacement['id'], 'amount': '1', 'unit': 'kg'}]))

    preview = inventory.service.measurement_correction(inventory.tokens['owner'], corrected['id'])
    assert preview['recipeCount'] == 0 and preview['canChangeUnit']
    changed = inventory.service.correct_measurement(
        inventory.tokens['owner'], corrected['id'], correction(inventory, corrected))
    assert changed['baseUnit'] == 'g'
    with inventory.connect() as connection:
        assert connection.execute(
            'SELECT base_unit FROM production_recipe_ingredients WHERE revision_id=%s AND product_id=%s',
            (recipe['revisionId'], corrected['id']),
        ).fetchone() == ('kg',)


def test_catalog_links_block_correction(inventory):
    source = create(inventory, sku='LINK-SOURCE')
    target = create(inventory, sku='LINK-TARGET')
    with inventory.connect() as connection:
        connection.execute(
            'UPDATE inventory_products SET canonical_product_id=%s WHERE id=%s',
            (target['id'], source['id']),
        )
    for item in (source, target):
        preview = inventory.service.measurement_correction(inventory.tokens['owner'], item['id'])
        assert not preview['canChangeUnit'] and measurement_corrections.LINK_ISSUE in preview['issues']


def test_correction_and_count_creation_share_the_policy_lock(inventory, monkeypatch):
    item = create(inventory)
    shelf = inventory.service.create_shelf(inventory.tokens['owner'], fields(inventory, name='Concurrent shelf'))
    inventory.service.place(inventory.tokens['owner'], shelf['id'], item['id'], fields(
        inventory, version=shelf['version'], active=True))
    entered, release = Event(), Event()
    original = measurement_corrections._inspect

    def pause_after_authorization(*args, **kwargs):
        result = original(*args, **kwargs)
        if kwargs.get('lock'):
            entered.set()
            assert release.wait(5)
        return result

    monkeypatch.setattr(measurement_corrections, '_inspect', pause_after_authorization)
    with ThreadPoolExecutor(max_workers=2) as pool:
        changed = pool.submit(
            inventory.service.correct_measurement, inventory.tokens['owner'], item['id'], correction(inventory, item))
        assert entered.wait(3)
        count = pool.submit(
            inventory.counts.start, inventory.tokens['owner'], fields(inventory, businessDate='2026-10-02'))
        assert not count.done()
        release.set()
        assert changed.result(timeout=5)['baseUnit'] == 'g'
        created = count.result(timeout=5)

    with inventory.connect() as connection:
        assert connection.execute(
            'SELECT base_unit FROM inventory_count_products WHERE count_id=%s AND product_id=%s',
            (created['id'], item['id']),
        ).fetchone() == ('g',)
