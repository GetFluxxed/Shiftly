from decimal import Decimal
from uuid import uuid4
import shutil

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate


def write(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def create(i, base='kg', **values):
    return i.service.create_product(i.tokens['owner'], write(i, **{
        'name': 'Flour', 'sku': str(uuid4()), 'baseUnit': base, **values}))


def test_pounds_are_labels_while_canonical_amount_stays_metric(inventory):
    product = create(inventory, containerAmount='50', containerUnit='lb')
    assert (product['containerAmount'], product['containerLabelAmount'], product['containerLabelUnit']) == (
        '22.6796185', '50', 'lb')
    default = next(item for item in inventory.service.packages(
        inventory.tokens['owner'], product['id'])['items'] if item['isDefault'])
    assert (default['amount'], default['labelAmount'], default['labelUnit']) == ('22.6796185', '50', 'lb')

    renamed = inventory.service.edit_product(inventory.tokens['owner'], product['id'], write(
        inventory, version=product['version'], name='Bread Flour', sku=product['sku']))
    assert (renamed['containerLabelAmount'], renamed['containerLabelUnit']) == ('50', 'lb')

    canonical_edit = inventory.service.edit_product(inventory.tokens['owner'], product['id'], write(
        inventory, version=renamed['version'], name='Bread Flour 2', sku=product['sku'],
        containerAmount=renamed['containerAmount']))
    assert (canonical_edit['containerLabelAmount'], canonical_edit['containerLabelUnit']) == ('50', 'lb')


def test_pounds_convert_to_grams_and_package_labels_survive_lookup_and_name_edit(inventory):
    product = create(inventory, 'g', containerAmount='50', containerUnit='lb')
    assert product['containerAmount'] == '22679.6185'
    option = inventory.service.create_package(inventory.tokens['owner'], product['id'], write(
        inventory, name='Small bag', kind='box', amount='0.25', amountUnit='lb', barcode='LB-BAG'))
    found = inventory.service.lookup_product(inventory.tokens['crew'], sku='LB-BAG')['package']
    assert (found['labelAmount'], found['labelUnit']) == ('0.25', 'lb')
    renamed = inventory.service.edit_package(inventory.tokens['owner'], product['id'], option['id'], write(
        inventory, version=option['version'], name='Small bag renamed', kind='box', amount=option['amount']))
    assert (renamed['labelAmount'], renamed['labelUnit']) == ('0.25', 'lb')


def test_default_archive_and_restore_clears_and_restores_product_label(inventory):
    product = create(inventory, containerAmount='25', containerUnit='lb')
    default = next(item for item in inventory.service.packages(
        inventory.tokens['owner'], product['id'])['items'] if item['isDefault'])
    archived = inventory.service.package_state(inventory.tokens['owner'], product['id'], default['id'], write(
        inventory, version=default['version'], active=False))
    cleared = inventory.service.product(inventory.tokens['owner'], product['id'])
    assert cleared['containerAmount'] is None and cleared['containerLabelUnit'] is None
    inventory.service.package_state(inventory.tokens['owner'], product['id'], default['id'], write(
        inventory, version=archived['version'], active=True))
    restored = inventory.service.product(inventory.tokens['owner'], product['id'])
    assert (restored['containerLabelAmount'], restored['containerLabelUnit']) == ('25', 'lb')


def test_package_rounding_case_and_default_mirroring(inventory):
    product = create(inventory, containerAmount='1')
    bag = inventory.service.create_package(inventory.tokens['owner'], product['id'], write(
        inventory, name='Quarter pound', kind='box', amount='0.25', amountUnit='lb'))
    assert (bag['amount'], bag['labelAmount'], bag['labelUnit']) == ('0.113398093', '0.25', 'lb')
    case = inventory.service.create_package(inventory.tokens['owner'], product['id'], write(
        inventory, name='Case', kind='case', containedPackageId=bag['id'], containedCount=10))
    assert case['amount'] == '1.13398093' and case['labelAmount'] is None

    default = next(item for item in inventory.service.packages(
        inventory.tokens['owner'], product['id'])['items'] if item['isDefault'])
    changed = inventory.service.edit_package(inventory.tokens['owner'], product['id'], default['id'], write(
        inventory, version=default['version'], name=default['name'], kind=default['kind'],
        amount='25', amountUnit='lb'))
    mirrored = inventory.service.product(inventory.tokens['owner'], product['id'])
    assert mirrored['containerAmount'] == changed['amount'] == '11.33980925'
    assert (mirrored['containerLabelAmount'], mirrored['containerLabelUnit']) == ('25', 'lb')


@pytest.mark.parametrize('base,amount,unit', [
    ('each', '2', 'lb'), ('kg', '2', 'each'), ('kg', '-1', 'lb'), ('kg', '2', 'stone')])
def test_incompatible_unknown_and_negative_units_are_rejected(inventory, base, amount, unit):
    with pytest.raises(IdentityError):
        create(inventory, base, containerAmount=amount, containerUnit=unit)


def test_leaf_package_requires_an_explicit_amount(inventory):
    product = create(inventory)
    with pytest.raises(IdentityError):
        inventory.service.create_package(inventory.tokens['owner'], product['id'], write(
            inventory, name='Missing', kind='box'))


def test_upgrade_024_preserves_existing_metric_package_and_stock(empty_database, tmp_path):
    before_024 = tmp_path / 'before-024'
    before_024.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        if path.name < '024':
            shutil.copy2(path, before_024 / path.name)
    connect = lambda: psycopg.connect(empty_database)
    migrate(connect, directory=before_024)
    product_id, package_id, count_id, movement_id = (str(uuid4()) for _ in range(4))
    with connect() as connection:
        business = connection.execute("INSERT INTO businesses(name) VALUES('Existing') RETURNING id").fetchone()[0]
        store = connection.execute("""INSERT INTO stores(name,access_code_hash,business_id)
            VALUES('Store',repeat('a',64),%s) RETURNING id""", (business,)).fetchone()[0]
        user = connection.execute("""INSERT INTO account_users(username,display_name,password_salt,password_hash)
            VALUES('weight-owner','Owner','salt','hash') RETURNING id""").fetchone()[0]
        connection.execute("""INSERT INTO inventory_products
            (id,business_id,sku,name,base_unit,container_amount) VALUES(%s,%s,'OLD-KG','Old kg','kg',6)""",
            (product_id, business))
        connection.execute("""INSERT INTO inventory_packages
            (id,business_id,product_id,name,amount,kind,is_default) VALUES(%s,%s,%s,'Container',6,'container',true)""",
            (package_id, business, product_id))
        connection.execute('''INSERT INTO inventory_product_skus(business_id,product_id,sku,package_id)
            VALUES(%s,%s,'OLD-KG',%s)''', (business, product_id, package_id))
        connection.execute('''INSERT INTO inventory_store_products(business_id,store_id,product_id)
            VALUES(%s,%s,%s)''', (business, store, product_id))
        connection.execute("""INSERT INTO inventory_counts
            (id,business_id,store_id,business_date,state,configuration_hash,started_by)
            VALUES(%s,%s,%s,'2026-10-01','draft',repeat('b',64),%s)""",
            (count_id, business, store, user))
        connection.execute('''INSERT INTO inventory_count_products
            (business_id,store_id,count_id,product_id,name,sku,base_unit,container_amount,
             product_version,previous_quantity,previous_count_id,previous_stock_version)
            VALUES(%s,%s,%s,%s,'Old kg','OLD-KG','kg',6,1,NULL,NULL,NULL)''',
            (business, store, count_id, product_id))
        connection.execute("""INSERT INTO inventory_stock_movements
            (id,business_id,store_id,product_id,base_unit,kind,source_id,quantity_before,quantity_after,version,actor_user_id)
            VALUES(%s,%s,%s,%s,'kg','opening',%s,NULL,12.5,1,%s)""",
            (movement_id, business, store, product_id, count_id, user))
        connection.execute("UPDATE inventory_counts SET state='review' WHERE id=%s", (count_id,))
        connection.execute('''INSERT INTO inventory_stock_postings
            (business_id,store_id,count_id,product_id,quantity_before,quantity_after,posted_by)
            VALUES(%s,%s,%s,%s,NULL,12.5,%s)''', (business, store, count_id, product_id, user))
        connection.execute("""INSERT INTO inventory_stock_balances
            (business_id,store_id,product_id,count_id,quantity,base_unit,counted_on,version,last_movement_id,last_counted_at)
            VALUES(%s,%s,%s,%s,12.5,'kg','2026-10-01',1,%s,NOW())""",
            (business, store, product_id, count_id, movement_id))
    assert migrate(connect) == ['024_inventory_package_weight_units.sql']
    with connect() as connection:
        assert connection.execute('''SELECT p.container_amount,p.container_label_amount,k.amount,k.label_amount,b.quantity
            FROM inventory_products p JOIN inventory_packages k ON k.product_id=p.id
            JOIN inventory_stock_balances b ON b.product_id=p.id''').fetchone() == (
                Decimal('6'), None, Decimal('6'), None, Decimal('12.5'))
