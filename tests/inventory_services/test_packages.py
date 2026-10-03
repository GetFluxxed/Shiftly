from uuid import UUID, uuid4
import shutil

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate


def write(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def product(i, **values):
    return i.service.create_product(i.tokens['owner'], write(i, **{
        'name': 'Rice', 'sku': str(uuid4()), 'baseUnit': 'g', **values}))


def package(i, product_id, **values):
    return i.service.create_package(i.tokens['owner'], product_id, write(i, **{
        'name': 'Bag', 'kind': 'box', 'amount': '1000', **values}))


def test_default_package_keeps_product_identity_and_exact_amount(inventory):
    item = product(inventory, containerAmount='1000.000000')
    options = inventory.service.packages(inventory.tokens['crew'], item['id'])
    assert options['nextCursor'] is None
    assert options['items'] == [{
        'id': options['items'][0]['id'], 'productId': item['id'], 'name': 'Container',
        'amount': '1000', 'labelAmount': None, 'labelUnit': None,
        'kind': 'container', 'active': True, 'version': 1,
        'isDefault': True, 'containedPackageId': None, 'containedCount': None,
        'barcodes': [item['sku']],
    }]


def test_case_amount_is_computed_and_snapshot_survives_archived_dependency_edit(inventory):
    item = product(inventory)
    leaf = package(inventory, item['id'], barcode='LEAF-1000')
    case = package(inventory, item['id'], name='Case of 10', kind='case', amount=None,
                   containedPackageId=leaf['id'], containedCount=10, barcode='CASE-10')
    assert case['amount'] == '10000'
    with pytest.raises(IdentityError) as used:
        inventory.service.edit_package(inventory.tokens['owner'], item['id'], leaf['id'], write(
            inventory, version=leaf['version'], name='Bag', kind='box', amount='900'))
    assert used.value.reason == 'state_conflict'
    archived = inventory.service.package_state(inventory.tokens['owner'], item['id'], case['id'], write(
        inventory, version=case['version'], active=False))
    changed = inventory.service.edit_package(inventory.tokens['owner'], item['id'], leaf['id'], write(
        inventory, version=leaf['version'], name='Bag', kind='box', amount='900'))
    with pytest.raises(IdentityError) as stale_conversion:
        inventory.service.package_state(inventory.tokens['owner'], item['id'], case['id'], write(
            inventory, version=archived['version'], active=True))
    assert stale_conversion.value.reason == 'state_conflict'
    refreshed = inventory.service.edit_package(inventory.tokens['owner'], item['id'], case['id'], write(
        inventory, version=archived['version'], name=case['name'], kind='case',
        containedPackageId=changed['id'], containedCount=10))
    assert refreshed['amount'] == '9000'


def test_barcode_lookup_returns_exact_package_and_reserves_archived_alias(inventory):
    item = product(inventory)
    bag = package(inventory, item['id'], barcode='BAG-CODE')
    found = inventory.service.lookup_product(inventory.tokens['crew'], sku='bag-code')
    assert found['product']['id'] == item['id'] and found['package'] == bag
    archived = inventory.service.package_state(inventory.tokens['owner'], item['id'], bag['id'], write(
        inventory, version=bag['version'], active=False))
    assert inventory.service.lookup_product(inventory.tokens['crew'], sku='BAG-CODE')['package'] == archived
    other = product(inventory)
    with pytest.raises(IdentityError) as collision:
        package(inventory, other['id'], barcode='BAG-CODE')
    assert collision.value.reason == 'duplicate_identifier'


def test_package_scope_permissions_stale_versions_and_product_version(inventory):
    item = product(inventory)
    created = package(inventory, item['id'])
    assert inventory.service.product(inventory.tokens['owner'], item['id'])['version'] == 2
    with pytest.raises(IdentityError) as hidden:
        inventory.service.packages(inventory.tokens['foreign'], item['id'])
    assert hidden.value.code == 'not_found'
    with pytest.raises(IdentityError) as denied:
        inventory.service.create_package(
            inventory.tokens['crew'], item['id'], write(inventory, name='No', kind='box', amount='1'))
    assert denied.value.code == 'forbidden'
    edited = inventory.service.edit_package(inventory.tokens['owner'], item['id'], created['id'], write(
        inventory, version=created['version'], name='Bag 2', kind='box', amount='1200'))
    with pytest.raises(IdentityError) as stale:
        inventory.service.edit_package(inventory.tokens['owner'], item['id'], created['id'], write(
            inventory, version=created['version'], name='Bad', kind='box', amount='1300'))
    assert stale.value.reason == 'stale_record' and edited['version'] == 2


def test_package_limit_includes_archived_options(inventory):
    item = product(inventory)
    for number in range(40):
        option = package(inventory, item['id'], name=f'Bag {number}', amount=str(number + 1))
        if number == 0:
            inventory.service.package_state(inventory.tokens['owner'], item['id'], option['id'], write(
                inventory, version=option['version'], active=False))
    with pytest.raises(IdentityError):
        package(inventory, item['id'], name='Overflow')


def test_default_package_active_state_is_the_legacy_container_amount(inventory):
    item = product(inventory, containerAmount='1000')
    default = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    archived = inventory.service.package_state(inventory.tokens['owner'], item['id'], default['id'], write(
        inventory, version=default['version'], active=False))
    assert inventory.service.product(inventory.tokens['owner'], item['id'])['containerAmount'] is None
    changed = inventory.service.edit_package(inventory.tokens['owner'], item['id'], default['id'], write(
        inventory, version=archived['version'], name='Container', kind='container', amount='900'))
    assert changed['active'] is False
    assert inventory.service.product(inventory.tokens['owner'], item['id'])['containerAmount'] is None
    restored = inventory.service.package_state(inventory.tokens['owner'], item['id'], default['id'], write(
        inventory, version=changed['version'], active=True))
    assert restored['amount'] == '900'
    assert inventory.service.product(inventory.tokens['owner'], item['id'])['containerAmount'] == '900'


def test_legacy_container_edit_clears_and_reactivates_the_same_default(inventory):
    item = product(inventory, containerAmount='1000')
    original = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    cleared = inventory.service.edit_product(inventory.tokens['owner'], item['id'], write(
        inventory, version=item['version'], name=item['name'], sku=item['sku'], containerAmount=None))
    archived = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    assert cleared['containerAmount'] is None and archived['id'] == original['id'] and not archived['active']
    restored = inventory.service.edit_product(inventory.tokens['owner'], item['id'], write(
        inventory, version=cleared['version'], name=item['name'], sku=item['sku'], containerAmount='750'))
    default = inventory.service.packages(inventory.tokens['owner'], item['id'])['items'][0]
    assert restored['containerAmount'] == '750'
    assert default['id'] == original['id'] and default['active'] and default['amount'] == '750'


def test_referenced_leaf_cannot_become_a_nested_or_self_contained_case(inventory):
    item = product(inventory)
    leaf = package(inventory, item['id'])
    package(inventory, item['id'], name='Case', kind='case', amount=None,
            containedPackageId=leaf['id'], containedCount=1)
    with pytest.raises(IdentityError) as nested:
        inventory.service.edit_package(inventory.tokens['owner'], item['id'], leaf['id'], write(
            inventory, version=leaf['version'], name='Nested', kind='case',
            containedPackageId=leaf['id'], containedCount=1))
    assert nested.value.code == 'invalid'


def test_package_name_and_barcode_are_catalog_searchable(inventory):
    item = product(inventory, name='Ingredient')
    package(inventory, item['id'], name='Wholesale carton', barcode='UNIQUE-BARCODE')
    assert inventory.service.products(inventory.tokens['crew'], query='carton')['items'][0]['id'] == item['id']
    assert inventory.service.products(inventory.tokens['crew'], query='unique-bar')['items'][0]['id'] == item['id']


def test_upgrade_020_seeds_packages_without_rewriting_catalog_count_or_stock_history(
        empty_database, tmp_path):
    before_021 = tmp_path / 'before-021'
    before_021.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        if path.name <= '020_production_accounts.sql':
            shutil.copy2(path, before_021 / path.name)
    connect = lambda: psycopg.connect(empty_database)
    migrate(connect, directory=before_021)
    product_id, count_id, movement_id = str(uuid4()), str(uuid4()), str(uuid4())
    with connect() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES('Existing') RETURNING id").fetchone()[0]
        store = connection.execute("""INSERT INTO stores(name,access_code_hash,business_id)
            VALUES('Store',repeat('a',64),%s) RETURNING id""", (business,)).fetchone()[0]
        user = connection.execute("""INSERT INTO account_users(username,display_name,password_salt,password_hash)
            VALUES('owner','Owner','salt','hash') RETURNING id""").fetchone()[0]
        connection.execute("""INSERT INTO inventory_products
            (id,business_id,sku,name,base_unit,container_amount,version)
            VALUES(%s,%s,'RICE-OLD','Rice','g',1000,7)""", (product_id,business))
        connection.execute("INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,'RICE-OLD')",
                           (business,product_id))
        connection.execute("INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)",
                           (business,store,product_id))
        connection.execute("""INSERT INTO inventory_counts
            (id,business_id,store_id,business_date,state,configuration_hash,started_by)
            VALUES(%s,%s,%s,'2026-09-01','draft',repeat('b',64),%s)""",
            (count_id,business,store,user))
        connection.execute("""INSERT INTO inventory_count_products
            (business_id,store_id,count_id,product_id,name,sku,base_unit,container_amount,
             product_version,previous_quantity,previous_count_id,previous_stock_version)
            VALUES(%s,%s,%s,%s,'Rice','RICE-OLD','g',1000,7,NULL,NULL,NULL)""",
            (business,store,count_id,product_id))
        connection.execute("UPDATE inventory_counts SET state='review' WHERE id=%s", (count_id,))
        connection.execute("""INSERT INTO inventory_stock_postings
            (business_id,store_id,count_id,product_id,quantity_before,quantity_after,posted_by)
            VALUES(%s,%s,%s,%s,NULL,12,%s)""", (business,store,count_id,product_id,user))
        connection.execute("""INSERT INTO inventory_stock_movements
            (id,business_id,store_id,product_id,base_unit,kind,source_id,quantity_before,
             quantity_after,version,actor_user_id)
            VALUES(%s,%s,%s,%s,'g','opening',%s,NULL,12,1,%s)""",
            (movement_id,business,store,product_id,count_id,user))
        connection.execute("""INSERT INTO inventory_stock_balances
            (business_id,store_id,product_id,count_id,quantity,base_unit,counted_on,version,
             last_movement_id,last_counted_at)
            VALUES(%s,%s,%s,%s,12,'g','2026-09-01',1,%s,NOW())""",
            (business,store,product_id,count_id,movement_id))
        before = {
            'product': connection.execute('SELECT id,base_unit,container_amount,version FROM inventory_products').fetchall(),
            'skus': connection.execute('SELECT business_id,product_id,sku FROM inventory_product_skus').fetchall(),
            'count': connection.execute('SELECT name,sku,base_unit,container_amount,product_version FROM inventory_count_products').fetchall(),
            'posting': connection.execute('SELECT quantity_before,quantity_after FROM inventory_stock_postings').fetchall(),
            'movement': connection.execute('SELECT id,quantity_before,quantity_after,version FROM inventory_stock_movements').fetchall(),
            'balance': connection.execute('SELECT quantity,base_unit,version,last_movement_id FROM inventory_stock_balances').fetchall(),
        }
    upgrade = tmp_path / 'upgrade'
    upgrade.mkdir()
    shutil.copy2(MIGRATIONS / '021_inventory_packages.sql', upgrade / '021_inventory_packages.sql')
    assert migrate(connect, directory=upgrade) == ['021_inventory_packages.sql']
    with connect() as connection:
        assert connection.execute('SELECT product_id,name,amount,is_default FROM inventory_packages').fetchall() == [
            (UUID(product_id), 'Container', 1000, True)]
        assert connection.execute('SELECT package_id IS NOT NULL FROM inventory_product_skus').fetchone() == (True,)
        assert connection.execute('SELECT packages FROM inventory_count_products').fetchone() == ([],)
        assert before == {
            'product': connection.execute('SELECT id,base_unit,container_amount,version FROM inventory_products').fetchall(),
            'skus': connection.execute('SELECT business_id,product_id,sku FROM inventory_product_skus').fetchall(),
            'count': connection.execute('SELECT name,sku,base_unit,container_amount,product_version FROM inventory_count_products').fetchall(),
            'posting': connection.execute('SELECT quantity_before,quantity_after FROM inventory_stock_postings').fetchall(),
            'movement': connection.execute('SELECT id,quantity_before,quantity_after,version FROM inventory_stock_movements').fetchall(),
            'balance': connection.execute('SELECT quantity,base_unit,version,last_movement_id FROM inventory_stock_balances').fetchall(),
        }
