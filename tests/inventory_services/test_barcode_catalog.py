from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from backend.shiftly.identity.contracts import IdentityError


def fields(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def create(i, sku, barcode_type=None, **values):
    data = fields(i, **{'name': 'Scanned product', 'sku': sku, 'baseUnit': 'each', **values})
    if barcode_type is not None:
        data['barcodeType'] = barcode_type
    return i.service.create_product(i.tokens['owner'], data)


def test_lookup_matches_current_alias_and_archived_product(inventory):
    i = inventory
    original = create(i, '036000291452', 'upc_a')
    renamed = i.service.edit_product(i.tokens['owner'], original['id'], fields(
        i, version=1, name='Renamed', sku='LEGACY-ALIAS'))
    archived = i.service.product_state(i.tokens['owner'], original['id'], fields(i, version=2, active=False))

    assert i.service.lookup_product(i.tokens['crew'], sku='036000291452', barcode_type='upc_a') == {
        'sku': '0036000291452', 'product': archived, 'package': None}
    assert i.service.lookup_product(i.tokens['crew'], sku='legacy-alias') == {
        'sku': 'legacy-alias', 'product': archived, 'package': None}
    assert renamed['id'] == archived['id']


def test_lookup_missing_auth_scope_and_company_isolation(inventory):
    i = inventory
    product = create(i, '0036000291452')
    assert i.service.lookup_product(i.tokens['crew'], sku='MISSING') == {
        'sku': 'MISSING', 'product': None, 'package': None}
    assert i.service.lookup_product(i.tokens['foreign'], sku='0036000291452')['product'] is None
    with pytest.raises(IdentityError) as denied:
        i.service.lookup_product(i.tokens['noinventory'], sku='0036000291452')
    assert denied.value.code == 'forbidden'
    with pytest.raises(IdentityError) as anonymous:
        i.service.lookup_product(None, sku=product['sku'])
    assert anonymous.value.code == 'unauthenticated'


@pytest.mark.parametrize(('sku', 'kind'), [
    ('036000291453', 'upc_a'), ('03600029145', 'upc_a'), ('4006381333932', 'ean13'),
    ('96385075', 'ean8'), ('12345678901232', 'itf14'), ('1234567', 'upc_e'),
    ('12345678', 'qr'), ('https://example.com', 'code128'),
])
def test_barcode_validation_is_strict_and_leaves_catalog_empty(inventory, sku, kind):
    with pytest.raises(IdentityError) as error:
        inventory.service.lookup_product(inventory.tokens['crew'], sku=sku, barcode_type=kind)
    assert error.value.code == 'invalid'
    assert inventory.service.products(inventory.tokens['owner'])['items'] == []


def test_upca_and_leading_zero_ean13_are_equivalent_on_lookup_and_create(inventory):
    i = inventory
    product = create(i, '036000291452', 'upc_a')
    assert product['sku'] == '0036000291452'
    assert i.service.lookup_product(i.tokens['crew'], sku='0036000291452', barcode_type='ean13')['product'] == product
    assert i.service.lookup_product(i.tokens['crew'], sku='0036000291452', barcode_type='upc_a')['product'] == product
    with pytest.raises(IdentityError) as duplicate:
        create(i, '0036000291452', 'ean13')
    assert duplicate.value.reason == 'duplicate_identifier'


@pytest.mark.parametrize(('printed', 'native', 'printed_type', 'native_type'), [
    ('085900233161', '085900233161', 'upc_a', 'ean13'),
    ('072965103249', '072965103249', 'upc_a', 'org.gs1.EAN-13'),
    ('652729105650', '652729105650', 'upc_a', 'VNBarcodeSymbologyEAN13'),
    ('0851085002553', '851085002553', 'ean13', 'ean13'),
    ('0817304018828', '817304018828', 'ean13', 'org.gs1.EAN-13'),
])
def test_photo_retail_codes_match_ios_shortened_and_full_platform_payloads(
        inventory, printed, native, printed_type, native_type):
    i = inventory
    expected = printed if len(printed) == 13 else '0' + printed
    product = create(i, printed, printed_type)

    assert product['sku'] == expected
    assert i.service.lookup_product(i.tokens['crew'], sku=printed, barcode_type=printed_type) == {
        'sku': expected, 'product': product, 'package': None}
    assert i.service.lookup_product(i.tokens['crew'], sku=native, barcode_type=native_type) == {
        'sku': expected, 'product': product, 'package': None}
    with i.connect() as connection:
        assert connection.execute(
            'SELECT count(DISTINCT product_id) FROM inventory_product_skus WHERE business_id=%s',
            (i.companies[0],)).fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM inventory_store_products').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_shelf_products').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_balances').fetchone()[0] == 0


@pytest.mark.parametrize('value', ['851085002554', '817304018829', '12345678901'])
def test_ios_shortened_ean13_requires_valid_upca_length_and_checksum(inventory, value):
    with pytest.raises(IdentityError) as error:
        inventory.service.lookup_product(inventory.tokens['crew'], sku=value, barcode_type='ean13')
    assert error.value.code == 'invalid'


@pytest.mark.parametrize(('native_type', 'canonical_type'), [
    ('code39', 'code39'), ('org.iso.Code39', 'code39'), ('VNBarcodeSymbologyCode39', 'code39'),
    ('code128', 'code128'), ('org.iso.Code128', 'code128'),
    ('code93', 'code93'), ('com.intermec.Code93', 'code93'),
])
def test_documented_native_linear_type_aliases_are_explicitly_allowed(inventory, native_type, canonical_type):
    i = inventory
    product = create(i, f'{canonical_type}-VALUE', canonical_type)
    assert i.service.lookup_product(i.tokens['crew'], sku=product['sku'], barcode_type=native_type)['product'] == product


@pytest.mark.parametrize('native_type', [
    'org.iso.QRCode', 'org.iso.Code93', 'Code93', 'Code128', 'code_39', 'CODE39',
    'org.ansi.Interleaved2of5', 'I2of5', '',
])
def test_unknown_or_out_of_scope_native_type_names_remain_rejected(inventory, native_type):
    with pytest.raises(IdentityError) as error:
        inventory.service.lookup_product(inventory.tokens['crew'], sku='12345670', barcode_type=native_type)
    assert error.value.code == 'invalid'


def test_native_alias_lookup_preserves_existing_shelf_count_and_product_identity(inventory):
    i = inventory
    product = create(i, '0851085002553', 'ean13', name='Existing counted product', baseUnit='kg')
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Counted shelf'))
    i.service.place(i.tokens['owner'], shelf['id'], product['id'], fields(
        i, version=shelf['version'], active=True))
    count = i.counts.start(i.tokens['owner'], fields(i, businessDate='2026-09-30'))

    with i.connect() as connection:
        before = tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in (
            'inventory_products', 'inventory_product_skus', 'inventory_shelf_products',
            'inventory_counts', 'inventory_count_lines', 'inventory_stock_balances',
            'inventory_stock_postings', 'inventory_stock_movements'))

    for barcode_type, payload in (
        ('ean13', '0851085002553'),
        ('ean13', '851085002553'),
        ('org.gs1.EAN-13', '851085002553'),
        ('VNBarcodeSymbologyEAN13', '851085002553'),
    ):
        found = i.service.lookup_product(i.tokens['crew'], sku=payload, barcode_type=barcode_type)
        assert found['sku'] == '0851085002553'
        assert found['product']['id'] == product['id']

    assert i.counts.detail(i.tokens['owner'], count['id'])['id'] == count['id']
    assert i.service.shelf(i.tokens['owner'], shelf['id'])['products']['items'][0]['id'] == product['id']
    with i.connect() as connection:
        after = tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in (
            'inventory_products', 'inventory_product_skus', 'inventory_shelf_products',
            'inventory_counts', 'inventory_count_lines', 'inventory_stock_balances',
            'inventory_stock_postings', 'inventory_stock_movements'))
    assert after == before


@pytest.mark.parametrize(('payload', 'native_type', 'canonical'), [
    ('6749118517', 'org.iso.Code39', '6749118517'),
    ('085900233161', 'ean13', '0085900233161'),
])
def test_native_http_lookup_create_lookup_and_same_request_replay(
        inventory, payload, native_type, canonical):
    i = inventory
    headers = {'Authorization': f'Bearer {i.tokens["owner"]}'}
    lookup = '/api/mobile/inventory/products/lookup'
    params = {'sku': payload, 'barcodeType': native_type}

    missing = i.client.get(lookup, headers=headers, params=params)
    assert missing.status_code == 200
    assert missing.json() == {'sku': canonical, 'product': None, 'package': None}

    request = {
        'requestId': str(uuid4()), 'expectedStoreId': i.stores[0],
        'name': 'Native photo product', 'sku': missing.json()['sku'],
        'barcodeType': native_type, 'baseUnit': 'each',
    }
    created = i.client.post('/api/mobile/inventory/products', headers=headers, json=request)
    assert created.status_code == 200, created.text
    product = created.json()
    assert product['sku'] == canonical

    replay = i.client.post('/api/mobile/inventory/products', headers=headers, json=request)
    assert replay.status_code == 200
    assert replay.json() == product

    found = i.client.get(lookup, headers=headers, params=params)
    assert found.status_code == 200
    assert found.json()['sku'] == canonical
    assert found.json()['product']['id'] == product['id']
    with i.connect() as connection:
        assert connection.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM inventory_store_products').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_shelf_products').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_balances').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_postings').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_movements').fetchone()[0] == 0


@pytest.mark.parametrize(('stored', 'native12', 'native13'), [
    ('00072488009455', '072488009455', '0072488009455'),
    ('00072288146008', '072288146008', '0072288146008'),
    ('00074865752275', '074865752275', '0074865752275'),
    ('00072488999640', '072488999640', '0072488999640'),
])
def test_native_retail_scan_finds_existing_zero_padded_gtin14_without_mutation(
        inventory, stored, native12, native13):
    i = inventory
    product = create(i, stored)
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Existing shelf'))
    i.service.place(i.tokens['owner'], shelf['id'], product['id'], fields(
        i, version=shelf['version'], active=True))
    with i.connect() as connection:
        before = tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in (
            'inventory_products', 'inventory_product_skus', 'inventory_store_products',
            'inventory_shelf_products', 'inventory_stock_balances', 'inventory_stock_postings',
            'inventory_stock_movements'))

    for payload, barcode_type in ((native12, 'ean13'), (native13, 'ean13'), (stored, 'itf14')):
        found = i.service.lookup_product(i.tokens['crew'], sku=payload, barcode_type=barcode_type)
        assert found['product']['id'] == product['id']
    assert i.service.lookup_product(i.tokens['foreign'], sku=native12, barcode_type='ean13')['product'] is None

    with i.connect() as connection:
        after = tuple(connection.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in (
            'inventory_products', 'inventory_product_skus', 'inventory_store_products',
            'inventory_shelf_products', 'inventory_stock_balances', 'inventory_stock_postings',
            'inventory_stock_movements'))
    assert after == before


def test_zero_padded_gtin_equivalence_is_shared_by_create_and_lookup(inventory):
    i = inventory
    product = create(i, '072488009455')
    assert i.service.lookup_product(i.tokens['crew'], sku='00072488009455', barcode_type='itf14')['product'] == product

    with pytest.raises(IdentityError) as duplicate:
        create(i, '072488009455', 'upc_a')
    assert duplicate.value.reason == 'duplicate_identifier'
    assert i.service.product(i.tokens['owner'], product['id']) == product


def test_distinct_manual_gtin_aliases_are_reported_as_ambiguous(inventory):
    i = inventory
    create(i, '072488009455')
    create(i, '00072488009455')
    with pytest.raises(IdentityError) as error:
        i.service.lookup_product(i.tokens['crew'], sku='0072488009455', barcode_type='ean13')
    assert error.value.reason == 'state_conflict'


def test_nonzero_itf14_packaging_indicator_is_not_a_retail_alias(inventory):
    i = inventory
    retail = create(i, '00072488009455')
    case = create(i, '10072488009452')
    assert i.service.lookup_product(i.tokens['crew'], sku='10072488009452', barcode_type='itf14')['product'] == case
    assert i.service.lookup_product(i.tokens['crew'], sku='072488009455', barcode_type='ean13')['product'] == retail
    with i.connect() as connection:
        aliases = connection.execute(
            'SELECT sku FROM inventory_product_skus WHERE product_id=%s ORDER BY sku', (case['id'],)).fetchall()
    assert aliases == [('10072488009452',)]


def test_manual_lookup_does_not_infer_gtin_equivalence(inventory):
    i = inventory
    product = create(i, '00072488009455')
    assert i.service.lookup_product(i.tokens['crew'], sku='00072488009455')['product'] == product
    assert i.service.lookup_product(i.tokens['crew'], sku='072488009455') == {
        'sku': '072488009455', 'product': None, 'package': None}


def test_ambiguous_legacy_equivalents_return_state_conflict(inventory):
    i = inventory
    create(i, '036000291452')
    create(i, '0036000291452')
    with pytest.raises(IdentityError) as error:
        i.service.lookup_product(i.tokens['crew'], sku='036000291452', barcode_type='upc_a')
    assert error.value.reason == 'state_conflict'
    with pytest.raises(IdentityError) as create_error:
        create(i, '036000291452', 'upc_a')
    assert create_error.value.reason == 'state_conflict'


def test_barcode_create_is_atomic_replayable_and_does_not_create_stock(inventory):
    i = inventory
    request = fields(i, name='Milk', sku='036000291452', barcodeType='upc_a', baseUnit='kg')
    first = i.service.create_product(i.tokens['owner'], request)
    assert i.service.create_product(i.tokens['owner'], request) == first
    with i.connect() as connection:
        assert connection.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM inventory_product_skus').fetchone()[0] == 3
        assert connection.execute('SELECT count(*) FROM inventory_changes').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM inventory_store_products').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_shelf_products').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_balances').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_postings').fetchone()[0] == 0
        assert connection.execute('SELECT count(*) FROM inventory_stock_movements').fetchone()[0] == 0


def test_concurrent_equivalent_scans_create_only_one_product(inventory):
    i = inventory
    requests = [
        fields(i, name='UPC', sku='036000291452', barcodeType='upc_a', baseUnit='each'),
        fields(i, name='EAN', sku='0036000291452', barcodeType='ean13', baseUnit='each'),
    ]
    def attempt(request):
        try:
            return i.service.create_product(i.tokens['owner'], request)
        except IdentityError as error:
            return error.reason
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, requests))
    assert sum(isinstance(result, dict) for result in results) == 1
    assert 'duplicate_identifier' in results
    with i.connect() as connection:
        assert connection.execute('SELECT count(*) FROM inventory_products').fetchone()[0] == 1
        assert connection.execute('SELECT count(*) FROM inventory_product_skus').fetchone()[0] == 3


def test_api_route_precedes_product_id_and_edit_rejects_barcode_type(inventory):
    i = inventory
    headers = {'Authorization': f'Bearer {i.tokens["owner"]}'}
    response = i.client.get('/api/mobile/inventory/products/lookup', headers=headers,
                            params={'sku': '036000291452', 'barcodeType': 'upc_a'})
    assert response.status_code == 200 and response.json() == {
        'sku': '0036000291452', 'product': None, 'package': None}
    product = create(i, 'MANUAL')
    with pytest.raises(IdentityError) as error:
        i.service.edit_product(i.tokens['owner'], product['id'], fields(
            i, version=1, name='No', sku='MANUAL', barcodeType='code128'))
    assert error.value.code == 'invalid'
