from decimal import Decimal
from uuid import uuid4
import shutil
import base64
import json

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.quantities import convert_mass
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate
from test_storage import fields


def create(i, **values):
    return i.service.create_product(i.tokens['owner'], fields(
        i, **{'name': 'White Quella', 'sku': str(uuid4()), 'baseUnit': 'kg', 'containerAmount': '6', **values}))


def test_container_amount_is_exact_shared_editable_and_audited(inventory):
    i = inventory
    product = create(i, containerAmount='6.000000')
    assert product['containerAmount'] == '6'
    assert i.service.product(i.second, product['id']) == product
    changed = i.service.edit_product(i.tokens['owner'], product['id'], fields(
        i, name=product['name'], sku=product['sku'], version=1, containerAmount='6.125'))
    assert changed['containerAmount'] == '6.125' and changed['id'] == product['id']
    retained = i.service.edit_product(i.tokens['owner'], product['id'], fields(
        i, name='White Quella renamed', sku=product['sku'], version=2))
    assert retained['containerAmount'] == '6.125'  # An older client never clears the amount.
    with pytest.raises(IdentityError) as stale:
        i.service.edit_product(i.tokens['owner'], product['id'], fields(
            i, name=product['name'], sku=product['sku'], version=1, containerAmount='10'))
    assert stale.value.reason == 'stale_record'
    with i.connect() as c:
        history = c.execute("SELECT before_value,after_value FROM inventory_changes WHERE operation='product.edited' ORDER BY id").fetchall()
        assert history[0][0]['containerAmount'] == '6'
        assert history[0][1]['containerAmount'] == '6.125'
        assert c.execute('SELECT container_amount FROM inventory_products WHERE id=%s', (product['id'],)).fetchone()[0] == Decimal('6.125')


@pytest.mark.parametrize('amount', [0, 6.1, True, '', '0', '-1', 'NaN', 'Infinity', '1e3', '1.0000001', '1000000000', '6 kg', {}, []])
def test_invalid_container_amounts_never_create_partial_product(inventory, amount):
    i = inventory
    with pytest.raises(IdentityError): create(i, containerAmount=amount)
    assert not i.service.products(i.tokens['owner'])['items']


def test_each_containers_require_whole_items_and_unknown_size_is_explicit(inventory):
    i = inventory
    assert create(i, baseUnit='each', containerAmount='12')['containerAmount'] == '12'
    with pytest.raises(IdentityError): create(i, baseUnit='each', containerAmount='0.5')
    assert create(i, containerAmount=None)['containerAmount'] is None
    for unit in ('ml', 'l'):
        with pytest.raises(IdentityError): create(i, baseUnit=unit)


@pytest.mark.parametrize('amount,unit,base,expected', [
    ('6', 'kg', 'g', '6000'), ('1250', 'g', 'kg', '1.25'), ('0.001', 'g', 'kg', '0.000001'),
    ('0.000001', 'g', 'kg', '0.000000001'), ('1.234567', 'kg', 'g', '1234.567'),
])
def test_future_partial_mass_conversion_preserves_exact_quantity(amount, unit, base, expected):
    assert convert_mass(amount, unit, base) == Decimal(expected)
    # Two full 6 kg containers plus 1,250 g partial share one SKU's kg total.
    assert Decimal(2) * Decimal(6) + convert_mass('1250', 'g', 'kg') == Decimal('13.25')


def test_mass_conversion_never_infers_volume_or_item_weight():
    for unit in ('each', 'ml', 'l'):
        with pytest.raises(IdentityError): convert_mass('1', unit, 'kg')


@pytest.mark.parametrize('amount', ['-1', 'NaN', 'Infinity', '0.0000001'])
def test_database_rejects_invalid_container_amounts(inventory, amount):
    i = inventory
    product = create(i)
    with pytest.raises(psycopg.errors.CheckViolation), i.connect() as c:
        c.execute('UPDATE inventory_products SET container_amount=%s WHERE id=%s', (amount, product['id']))


def test_alphabetical_catalog_pages_preserve_ties_search_and_cursor_position(inventory):
    i = inventory
    names = [f'Product {n:02}' for n in reversed(range(43))] + ['alpha', 'Alpha', 'Zebra']
    items = [create(i, name=name) for name in names]
    expected = sorted(items, key=lambda item: (item['name'].lower(), item['id']))
    first = i.service.products(i.tokens['owner'])
    second = i.service.products(i.tokens['owner'], after=first['nextCursor'])
    assert first['items'] + second['items'] == expected
    assert second['nextCursor'] is None
    assert i.service.products(i.tokens['owner'], query='ALPHA')['items'] == expected[:2]
    assert i.service.products(i.tokens['foreign'], after=first['nextCursor'])['items'] == []
    # Renaming the last seen product must not reinterpret the cursor's saved name.
    boundary = first['items'][-1]
    i.service.edit_product(i.tokens['owner'], boundary['id'], fields(
        i, name='A moved product', sku=boundary['sku'], version=1))
    assert i.service.products(i.tokens['owner'], after=first['nextCursor']) == second


@pytest.mark.parametrize('cursor', ['../accounts', 'p1.eA', 'p1.W10', 'p1.' + 'a' * 1300, str(uuid4()),
    'p1.' + base64.urlsafe_b64encode(json.dumps(['bad\x00name', str(uuid4())]).encode()).decode().rstrip('='),
    'p1.' + base64.urlsafe_b64encode(json.dumps(['bad\ud800name', str(uuid4())]).encode()).decode().rstrip('=')])
def test_invalid_or_old_product_cursor_requires_fresh_page(inventory, cursor):
    with pytest.raises(IdentityError) as error:
        inventory.service.products(inventory.tokens['owner'], after=cursor)
    assert error.value.code == 'invalid'


def test_upgrade_015_preserves_products_without_inventing_container_sizes(empty_database, tmp_path):
    old = tmp_path/'old'; old.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        if path.name < '016': shutil.copy2(path, old/path.name)
    connect = lambda: psycopg.connect(empty_database)
    assert len(migrate(connect, directory=old)) == 15
    ids = [str(uuid4()), str(uuid4())]
    with connect() as c:
        business = c.execute("INSERT INTO businesses(name) VALUES('Existing') RETURNING id").fetchone()[0]
        for product_id, unit in zip(ids, ('kg', 'l')):
            c.execute('INSERT INTO inventory_products(id,business_id,sku,name,base_unit,version) VALUES(%s,%s,%s,%s,%s,3)',
                      (product_id, business, product_id, 'Existing '+unit, unit))
            c.execute('INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,%s)', (business, product_id, product_id))
    assert migrate(connect) == ['016_product_container_amounts.sql']
    assert migrate(connect) == []
    with connect() as c:
        rows = c.execute('SELECT base_unit,version,container_amount FROM inventory_products ORDER BY base_unit').fetchall()
        assert rows == [('kg', 3, None), ('l', 3, None)]


def test_retry_of_pre_container_request_preserves_saved_result(inventory):
    i = inventory
    request = fields(i, name='Existing request', sku='OLD-REQUEST', baseUnit='kg')
    original = i.service.create_product(i.tokens['owner'], request)
    # A migration-015 client sent no containerAmount and stored the older response shape.
    with i.connect() as c:
        c.execute("UPDATE inventory_requests SET result=result-'containerAmount' WHERE request_id=%s", (request['requestId'],))
    replay = i.service.create_product(i.tokens['owner'], request)
    assert replay['id'] == original['id'] and 'containerAmount' not in replay
    assert len(i.service.products(i.tokens['owner'])['items']) == 1
