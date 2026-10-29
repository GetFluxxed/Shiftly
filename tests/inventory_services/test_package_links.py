from uuid import uuid4

import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.package_links import combine, preview
from backend.shiftly.production.service import ProductionService
from tests.inventory_services.test_counts import (
    observe_all as observe_count, post as post_count, setup_stock,
    start as start_count,
)


def fields(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def product(i, name, sku, unit='kg', amount=None):
    values = {'name': name, 'sku': sku, 'baseUnit': unit}
    if amount is not None:
        values['containerAmount'] = amount
    return i.service.create_product(i.tokens['owner'], fields(i, **values))


def confirm(i, source, target, **extra):
    return fields(i, targetProductId=target['id'], sourceVersion=source['version'],
                  targetVersion=target['version'], confirmed=True, **extra)


def test_owner_previews_and_combines_package_identity_without_rewriting_aliases(inventory):
    source = product(inventory, 'Bacio Base 50MB', 'BACIO-25', amount='2.5')
    target = product(inventory, 'Bacio Base', 'BACIO-20', amount='2')
    package = inventory.service.packages(inventory.tokens['owner'], source['id'])['items'][0]
    seen = preview(inventory.service, inventory.tokens['owner'], source['id'], target['id'])
    assert seen['canCombine'] is True and seen['shelves'] == 0
    assert seen['packages'][0]['id'] == package['id']

    result = combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(inventory, source, target))
    assert result['id'] == target['id'] and result['version'] == target['version'] + 1
    with inventory.connect() as db:
        linked = db.execute('SELECT active,canonical_product_id FROM inventory_products WHERE id=%s', (source['id'],)).fetchone()
        alias = db.execute('SELECT product_id,package_id FROM inventory_product_skus WHERE sku=%s', ('BACIO-25',)).fetchone()
        old = db.execute('SELECT active,redirect_package_id FROM inventory_packages WHERE id=%s', (package['id'],)).fetchone()
        copied = db.execute('SELECT product_id,name,amount,is_default FROM inventory_packages WHERE id=%s', (old[1],)).fetchone()
    assert linked[0] is False
    assert str(linked[1]) == target['id']
    assert str(alias[0]) == source['id'] and str(alias[1]) == package['id']
    assert old[0] is False and str(copied[0]) == target['id']
    assert copied[1] == 'Bacio Base 50MB' and str(copied[2]) == '2.5'
    assert copied[3] is False
    scanned = inventory.service.lookup_product(inventory.tokens['crew'], sku='BACIO-25')
    assert scanned['product']['id'] == target['id']
    assert scanned['package']['id'] == str(old[1])
    assert 'BACIO-25' in scanned['package']['barcodes']

    copied_option = scanned['package']
    edited = inventory.service.edit_package(
        inventory.tokens['owner'], target['id'], copied_option['id'], fields(
            inventory, version=copied_option['version'], name='Copied package renamed',
            kind=copied_option['kind'], amount=copied_option['amount'], barcode='BACIO-25'))
    assert edited['name'] == 'Copied package renamed' and 'BACIO-25' in edited['barcodes']
    with inventory.connect() as db:
        preserved = db.execute('''SELECT product_id,package_id FROM inventory_product_skus
            WHERE sku='BACIO-25' ''').fetchone()
    assert str(preserved[0]) == source['id'] and str(preserved[1]) == package['id']


def test_replay_is_idempotent_and_stale_versions_fail(inventory):
    source = product(inventory, 'Source', 'SOURCE', amount='1')
    target = product(inventory, 'Target', 'TARGET', amount='1')
    request = confirm(inventory, source, target)
    first = combine(inventory.service, inventory.tokens['owner'], source['id'], request)
    assert combine(inventory.service, inventory.tokens['owner'], source['id'], request) == first

    other_source = product(inventory, 'Other source', 'OTHER-S', amount='1')
    other_target = product(inventory, 'Other target', 'OTHER-T', amount='1')
    inventory.service.edit_product(inventory.tokens['owner'], other_source['id'], fields(
        inventory, version=other_source['version'], name='Changed', sku=other_source['sku']))
    with pytest.raises(IdentityError) as stale:
        combine(inventory.service, inventory.tokens['owner'], other_source['id'], confirm(
            inventory, other_source, other_target))
    assert stale.value.reason == 'stale_record'


def test_replay_rechecks_owner_after_demotion(inventory):
    source = product(inventory, 'Owner source', 'OWNER-S', amount='1')
    target = product(inventory, 'Owner target', 'OWNER-T', amount='1')
    request = confirm(inventory, source, target)
    combine(inventory.service, inventory.tokens['owner'], source['id'], request)
    with inventory.connect() as db:
        db.execute('''UPDATE business_memberships
            SET role='admin',capabilities=ARRAY['catalog.manage','inventory.view']
            WHERE user_id=%s AND business_id=%s''',
            (inventory.users['owner'], inventory.companies[0]))
        db.execute('''UPDATE account_store_memberships SET state='revoked'
            WHERE user_id=%s AND store_id=%s''',
            (inventory.users['owner'], inventory.stores[1]))
    with pytest.raises(IdentityError) as denied:
        combine(inventory.service, inventory.tokens['owner'], source['id'], request)
    assert denied.value.code == 'forbidden' and denied.value.reason == 'permission_denied'


@pytest.mark.parametrize('token_name', ['delegate', 'manager', 'crew'])
def test_only_owner_can_preview_or_confirm(inventory, token_name):
    source = product(inventory, 'Source', 'SOURCE-' + token_name, amount='1')
    target = product(inventory, 'Target', 'TARGET-' + token_name, amount='1')
    with pytest.raises(IdentityError) as denied:
        preview(inventory.service, inventory.tokens[token_name], source['id'], target['id'])
    assert denied.value.code == 'forbidden'
    with pytest.raises(IdentityError) as denied_write:
        combine(inventory.service, inventory.tokens[token_name], source['id'], confirm(inventory, source, target))
    assert denied_write.value.code == 'forbidden'


def test_foreign_products_and_same_product_are_rejected(inventory):
    source = product(inventory, 'Source', 'LOCAL-S', amount='1')
    target = product(inventory, 'Target', 'LOCAL-T', amount='1')
    with pytest.raises(IdentityError) as hidden:
        preview(inventory.service, inventory.tokens['foreign'], source['id'], target['id'])
    assert hidden.value.code in {'forbidden', 'not_found'}
    same = preview(inventory.service, inventory.tokens['owner'], source['id'], source['id'])
    assert same['canCombine'] is False and any('different' in issue for issue in same['issues'])


def test_mass_conversion_case_remap_and_store_placement_union(inventory):
    source = product(inventory, 'Gram bag', 'GRAM-BAG', unit='g', amount='2500')
    leaf = inventory.service.packages(inventory.tokens['owner'], source['id'])['items'][0]
    case = inventory.service.create_package(inventory.tokens['owner'], source['id'], fields(
        inventory, name='Case of 4', kind='case', containedPackageId=leaf['id'], containedCount=4))
    source = inventory.service.product(inventory.tokens['owner'], source['id'])
    target = product(inventory, 'Canonical kg', 'CANON-KG', unit='kg', amount='2')
    shelf = inventory.service.create_shelf(inventory.tokens['owner'], fields(inventory, name='Back stock'))
    inventory.service.place(inventory.tokens['owner'], shelf['id'], source['id'], fields(
        inventory, version=shelf['version'], active=True))

    combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(inventory, source, target))
    options = inventory.service.packages(inventory.tokens['owner'], target['id'])['items']
    copied_leaf = next(item for item in options if item['name'] == 'Gram bag')
    copied_case = next(item for item in options if item['name'] == 'Case of 4')
    assert copied_leaf['amount'] == '2.5' and copied_leaf['isDefault'] is False
    assert copied_case['amount'] == '10' and copied_case['containedPackageId'] == copied_leaf['id']
    with inventory.connect() as db:
        placements = db.execute('''SELECT product_id,active FROM inventory_shelf_products
            WHERE shelf_id=%s ORDER BY product_id''', (shelf['id'],)).fetchall()
        shelf_version = db.execute('SELECT version FROM inventory_shelves WHERE id=%s', (shelf['id'],)).fetchone()[0]
        audit = db.execute('''SELECT before_value,after_value FROM inventory_changes
            WHERE operation='product.combined' ORDER BY id DESC LIMIT 1''').fetchone()
    assert {str(row[0]): row[1] for row in placements} == {source['id']: False, target['id']: True}
    assert shelf_version == shelf['version'] + 2
    assert audit[0]['scope']['placements'] == [{
        'storeId': inventory.stores[0], 'shelfId': shelf['id'],
        'productId': source['id'], 'active': True,
    }]
    assert {row['productId']: row['active'] for row in audit[1]['scope']['placements']} == {
        source['id']: False, target['id']: True,
    }


def test_archived_case_preserves_recorded_amount_after_leaf_edit(inventory):
    source = product(inventory, 'Bulk source', 'BULK-S', unit='g', amount='1000')
    leaf = inventory.service.packages(inventory.tokens['owner'], source['id'])['items'][0]
    case = inventory.service.create_package(inventory.tokens['owner'], source['id'], fields(
        inventory, name='Legacy case', kind='case', containedPackageId=leaf['id'], containedCount=2))
    archived = inventory.service.package_state(inventory.tokens['owner'], source['id'], case['id'], fields(
        inventory, version=case['version'], active=False))
    inventory.service.edit_package(inventory.tokens['owner'], source['id'], leaf['id'], fields(
        inventory, version=leaf['version'], name=leaf['name'], kind=leaf['kind'], amount='900'))
    source = inventory.service.product(inventory.tokens['owner'], source['id'])
    target = product(inventory, 'Canonical bulk', 'BULK-T', unit='kg', amount='1')

    combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(inventory, source, target))
    options = inventory.service.packages(inventory.tokens['owner'], target['id'])['items']
    copied_leaf = next(item for item in options if item['name'] == 'Bulk source')
    copied_case = next(item for item in options if item['name'] == 'Legacy case')
    assert copied_leaf['amount'] == '0.9'
    assert copied_case['active'] is False and copied_case['amount'] == '2'
    assert copied_case['containedPackageId'] == copied_leaf['id']
    assert archived['amount'] == '2000'


def test_long_source_name_is_an_actionable_preview_issue(inventory):
    source = product(inventory, 'S' * 121, 'LONG-S', amount='1')
    target = product(inventory, 'Target', 'LONG-T', amount='1')
    result = preview(inventory.service, inventory.tokens['owner'], source['id'], target['id'])
    assert result['canCombine'] is False
    assert any('120 characters' in issue for issue in result['issues'])
    with pytest.raises(IdentityError) as blocked:
        combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(
            inventory, source, target))
    assert blocked.value.reason == 'state_conflict'


def test_count_history_on_either_product_blocks_without_mutation(inventory):
    source = product(inventory, 'Source', 'HISTORY-S', amount='1')
    target = product(inventory, 'Target', 'HISTORY-T', amount='1')
    shelf = inventory.service.create_shelf(inventory.tokens['owner'], fields(inventory, name='Count shelf'))
    inventory.service.place(inventory.tokens['owner'], shelf['id'], source['id'], fields(
        inventory, version=shelf['version'], active=True))
    count = inventory.counts.start(inventory.tokens['owner'], fields(inventory, businessDate='2026-10-01'))
    blocked = preview(inventory.service, inventory.tokens['owner'], source['id'], target['id'])
    assert blocked['canCombine'] is False and any('count snapshots' in issue for issue in blocked['issues'])
    with pytest.raises(IdentityError):
        combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(inventory, source, target))
    assert inventory.service.product(inventory.tokens['owner'], source['id'])['active'] is True
    assert count['state'] == 'draft'


def test_posted_balance_and_movements_on_target_block_without_mutation(inventory):
    target, _ = setup_stock(inventory)
    post_count(inventory, observe_count(inventory, start_count(inventory)))
    source = product(inventory, 'Uncounted source', 'POSTED-S', amount='2.5')
    blocked = preview(inventory.service, inventory.tokens['owner'], source['id'], target['id'])
    assert blocked['canCombine'] is False
    issue = ' '.join(blocked['issues'])
    assert 'count snapshots' in issue and 'stock balances' in issue and 'stock movements' in issue
    with pytest.raises(IdentityError):
        combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(
            inventory, source, target))
    assert inventory.service.product(inventory.tokens['owner'], source['id'])['active'] is True


def test_recipe_revision_reference_on_source_blocks_without_mutation(inventory):
    source = product(inventory, 'Recipe source', 'RECIPE-S', amount='1')
    target = product(inventory, 'Recipe target', 'RECIPE-T', amount='1')
    production = ProductionService(inventory.connect, inventory.accounts)
    production.create_recipe(inventory.tokens['owner'], fields(
        inventory, name='Referenced recipe', yieldAmount='1', yieldUnit='batch',
        instructions='', ingredients=[{'productId': source['id'], 'amount': '1', 'unit': 'kg'}]))
    blocked = preview(inventory.service, inventory.tokens['owner'], source['id'], target['id'])
    assert blocked['canCombine'] is False and any('recipe revisions' in issue for issue in blocked['issues'])
    with pytest.raises(IdentityError):
        combine(inventory.service, inventory.tokens['owner'], source['id'], confirm(
            inventory, source, target))
    assert inventory.service.product(inventory.tokens['owner'], source['id'])['active'] is True


def test_open_count_missing_package_name_conflict_and_chain_block(inventory):
    source = product(inventory, 'Container', 'BLOCK-S', amount='1')
    target = product(inventory, 'Target', 'BLOCK-T', amount='2')
    conflict = preview(inventory.service, inventory.tokens['owner'], source['id'], target['id'])
    assert conflict['canCombine'] is False and any('package name' in issue for issue in conflict['issues'])

    bare = product(inventory, 'Bare', 'BARE')
    missing = preview(inventory.service, inventory.tokens['owner'], bare['id'], target['id'])
    assert any('package size' in issue for issue in missing['issues'])

    with inventory.connect() as db:
        db.execute('UPDATE inventory_products SET canonical_product_id=%s,active=false WHERE id=%s', (target['id'], bare['id']))
    incoming = preview(inventory.service, inventory.tokens['owner'], target['id'], source['id'])
    assert any('linked to it' in issue for issue in incoming['issues'])
