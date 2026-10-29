from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

import pytest
import psycopg

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.receiving import ReceivingService
from backend.shiftly.runtime.migrate import migrate


def fields(i, store=None, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': store or i.stores[0], **values}


def denied(code, operation, reason=None):
    with pytest.raises(IdentityError) as caught:
        operation()
    assert caught.value.code == code
    if reason:
        assert caught.value.reason == reason
    return caught.value


def setup(inventory, *, base_unit='kg'):
    i = inventory
    service = ReceivingService(i.connect, i.accounts)
    product = i.service.create_product(i.tokens['owner'], fields(
        i, name='White Quella', sku='000184', baseUnit=base_unit))
    shelf = i.service.create_shelf(i.tokens['owner'], fields(i, name='Walk-in'))
    i.service.place(i.tokens['owner'], shelf['id'], product['id'], fields(
        i, version=shelf['version'], active=True))
    package = i.service.create_package(i.tokens['owner'], product['id'], fields(
        i, name='Six kilo tub', kind='box', amount='6' if base_unit == 'kg' else '6'))
    return service, product, package


def invoice_line(product=None, package=None, **values):
    return {'id': str(uuid4()), 'description': 'White Quella 6kg', 'sku': '000184',
            'productId': product['id'] if product else None,
            'packageId': package['id'] if package else None,
            'quantity': '2' if product else None, 'unit': 'package' if package else ('kg' if product else ''),
            'received': False, **values}


def test_draft_exact_projection_checkoff_close_and_no_stock_mutation(inventory):
    service, product, package = setup(inventory)
    body = fields(inventory, supplier='Dairy Co', invoiceNumber='INV-001',
                  lines=[invoice_line(product, package)])
    draft = service.create(inventory.tokens['owner'], body)
    assert draft['version'] == 1 and draft['lines'][0]['normalizedQuantity'] == '12'
    assert draft['lines'][0]['productName'] == 'White Quella'
    assert service.create(inventory.tokens['owner'], body) == draft
    incoming = service.incoming(inventory.tokens['owner'])
    assert incoming == {'items': [{'productId': product['id'], 'name': 'White Quella', 'baseUnit': 'kg',
        'currentQuantity': None, 'incomingQuantity': '12', 'receivedQuantity': '0', 'projectedQuantity': None}],
        'nextCursor': None, 'unmatchedCount': 0, 'needsCountReview': False, 'needsCatalogReview': False}
    assert inventory.counts.stock(inventory.tokens['owner'])['items'][0]['quantity'] is None
    saved = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=1, supplier='Dairy Co', invoiceNumber='INV-001',
        lines=[{**body['lines'][0], 'received': True}]))
    assert saved['version'] == 2
    assert service.incoming(inventory.tokens['owner'])['items'][0]['receivedQuantity'] == '12'
    closed = service.close(inventory.tokens['owner'], draft['id'], fields(inventory, version=2))
    assert closed['state'] == 'closed' and service.incoming(inventory.tokens['owner'])['items'] == []
    assert inventory.counts.stock(inventory.tokens['owner'])['items'][0]['quantity'] is None



def test_photo_availability_tracks_runtime_configuration_in_list_and_detail(inventory):
    service = ReceivingService(inventory.connect, inventory.accounts)
    token = inventory.tokens['owner']
    draft = service.create(token, fields(inventory, supplier='', invoiceNumber='', lines=[]))
    assert service.invoices(token)['photoReadingAvailable'] is False
    assert service.invoice(token, draft['id'])['photoReadingAvailable'] is False
    enabled = ReceivingService(inventory.connect, inventory.accounts, photo_reading_available=True)
    assert enabled.invoices(token)['photoReadingAvailable'] is True
    assert enabled.invoice(token, draft['id'])['photoReadingAvailable'] is True
    assert enabled.invoice(token, draft['id'])['version'] == draft['version']


def test_scope_duplicate_idempotency_stale_and_concurrent_edits(inventory):
    service, product, _ = setup(inventory)
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Supplier', invoiceNumber='A-1', lines=[invoice_line(product)]))
    denied('forbidden', lambda: service.invoices(inventory.tokens['crew']))
    assert service.invoices(inventory.second)['items'] == []
    denied('conflict', lambda: service.create(inventory.tokens['owner'], fields(
        inventory, supplier='supplier', invoiceNumber='a-1')), 'duplicate_identifier')
    edits = [fields(inventory, version=1, supplier='Supplier', invoiceNumber='A-1',
                    lines=[invoice_line(product)]) for _ in range(2)]
    def save(body):
        try:
            return service.edit(inventory.tokens['owner'], draft['id'], body)
        except IdentityError as error:
            return error.reason
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(save, edits))
    assert results.count('stale_record') == 1
    wrong = fields(inventory, version=2, supplier='Supplier', invoiceNumber='A-1', lines=[])
    wrong['expectedStoreId'] = inventory.stores[1]
    denied('conflict', lambda: service.edit(inventory.tokens['owner'], draft['id'], wrong), 'store_context_changed')


def test_unmatched_lines_and_package_change_require_explicit_rematch(inventory):
    service, product, package = setup(inventory)
    matched = invoice_line(product, package)
    unmatched = invoice_line(description='Handwritten mystery', received=True)
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='', invoiceNumber='', lines=[matched, unmatched]))
    assert service.incoming(inventory.tokens['owner'])['unmatchedCount'] == 1
    archived = inventory.service.package_state(inventory.tokens['owner'], product['id'], package['id'], fields(
        inventory, version=package['version'], active=False))
    inventory.service.edit_package(inventory.tokens['owner'], product['id'], package['id'], fields(
        inventory, version=archived['version'], name='Changed tub', kind='box', amount='7'))
    denied('conflict', lambda: service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=draft['version'], supplier='', invoiceNumber='', lines=[{**matched, 'received': True}, unmatched])))
    detail = service.invoice(inventory.tokens['owner'], draft['id'])
    assert detail['needsCountReview'] is False and detail['needsCatalogReview'] is True
    assert detail['lines'][0]['needsCatalogReview'] is True
    assert service.incoming(inventory.tokens['owner'])['items'] == []
    unmatched_saved = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=draft['version'], supplier='', invoiceNumber='',
        lines=[{**matched, 'productId': None, 'packageId': None, 'quantity': None, 'unit': ''}, unmatched]))
    recovered = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=unmatched_saved['version'], supplier='', invoiceNumber='',
        lines=[{**matched, 'id': str(uuid4()), 'packageId': None, 'quantity': '3', 'unit': 'kg'}, unmatched]))
    assert recovered['lines'][0]['normalizedQuantity'] == '3'


def test_posted_count_makes_projection_reviewable_until_explicit_rebase(inventory):
    service, product, _ = setup(inventory)
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Dairy', invoiceNumber='2', lines=[invoice_line(product, quantity='2', unit='kg')]))
    count = inventory.counts.start(inventory.tokens['owner'], fields(inventory, businessDate='2026-10-25'))
    line = inventory.counts.lines(inventory.tokens['owner'], count['id'])['items'][0]
    saved = inventory.counts.save(inventory.tokens['owner'], count['id'], line['id'], fields(
        inventory, version=line['version'], entry={'mode': 'total', 'amount': '10', 'unit': 'kg'}))
    reviewed = inventory.counts.transition(inventory.tokens['owner'], count['id'], 'review', fields(
        inventory, version=saved['count']['version']))
    inventory.counts.transition(inventory.tokens['owner'], count['id'], 'post', fields(
        inventory, version=reviewed['version']))
    stale = service.incoming(inventory.tokens['owner'])
    assert stale['needsCountReview'] is True and stale['items'][0]['currentQuantity'] == '10'
    assert stale['items'][0]['projectedQuantity'] is None
    rebased = service.rebase(inventory.tokens['owner'], draft['id'], fields(inventory, version=draft['version']))
    assert rebased['needsCountReview'] is False
    assert service.incoming(inventory.tokens['owner'])['items'][0]['projectedQuantity'] == '12'


def test_migration_is_additive_and_repeatable(inventory):
    service, _, _ = setup(inventory)
    draft = service.create(inventory.tokens['owner'], fields(inventory, supplier='Kept', invoiceNumber='7'))
    assert migrate(inventory.connect) == []
    assert service.invoice(inventory.tokens['owner'], draft['id'])['supplier'] == 'Kept'


def test_native_receiving_endpoints_use_bearer_auth_and_validation(inventory):
    _, product, _ = setup(inventory)
    headers = {'Authorization': 'Bearer ' + inventory.tokens['owner']}
    base = '/api/mobile/inventory'
    body = fields(inventory, supplier='API Dairy', invoiceNumber='API-1', lines=[invoice_line(product)])
    created = inventory.client.post(base + '/invoices', headers=headers, json=body)
    assert created.status_code == 200, created.text
    draft = created.json()
    assert inventory.client.get(base + '/invoices', headers=headers).json()['items'][0]['id'] == draft['id']
    assert inventory.client.get(base + '/incoming', headers=headers).json()['items'][0]['incomingQuantity'] == '2'
    assert inventory.client.get(base + '/invoices/' + draft['id'], headers=headers).status_code == 200
    assert inventory.client.post(base + '/invoices/' + draft['id'] + '/close', headers=headers,
                                 json=fields(inventory, version=draft['version'])).status_code == 200
    assert inventory.client.get(base + '/invoices', headers={}).status_code == 401
    assert inventory.client.post(base + '/invoices', headers=headers, json=[]).status_code == 400
    for cursor in ('not-base64', 'i1.' + 'x' * 1025, 'i1.WyJub3QtYS10aW1lIiwiYmFkIl0'):
        assert inventory.client.get(base + '/invoices', headers=headers, params={'after': cursor}).status_code == 400
    assert inventory.client.get(base + '/incoming', headers=headers, params={'after': 'r1.%%%'}).status_code == 400


def test_active_business_product_needs_no_store_listing_or_shelf(inventory):
    service = ReceivingService(inventory.connect, inventory.accounts)
    product = inventory.service.create_product(inventory.tokens['owner'], fields(
        inventory, name='Never shelved', sku='NEW-CATALOG', baseUnit='kg'))
    with inventory.connect() as db:
        db.execute('DELETE FROM inventory_store_products WHERE business_id=%s AND store_id=%s AND product_id=%s',
                   (inventory.companies[0], inventory.stores[0], product['id']))
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='New', invoiceNumber='1', lines=[invoice_line(product, quantity='1', unit='kg')]))
    assert draft['lines'][0]['productId'] == product['id']
    assert service.incoming(inventory.tokens['owner'])['items'][0]['currentQuantity'] is None


def test_cross_business_package_is_rejected(inventory):
    service, product, _ = setup(inventory)
    foreign = inventory.service.create_product(inventory.tokens['foreign'], fields(
        inventory, inventory.stores[2], name='Foreign', sku='FOREIGN-P', baseUnit='kg'))
    foreign_package = inventory.service.create_package(inventory.tokens['foreign'], foreign['id'], fields(
        inventory, inventory.stores[2], name='Foreign case', kind='box', amount='4'))
    denied('conflict', lambda: service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Bad', invoiceNumber='X',
        lines=[invoice_line(product, package=foreign_package)])))


@pytest.mark.parametrize('value', ['1e2', '+1', 'NaN', 'Infinity', '0.0000000001', '1000000000000000'])
def test_quantities_reject_non_plain_or_out_of_range_values(inventory, value):
    service, product, _ = setup(inventory)
    denied('invalid', lambda: service.create(inventory.tokens['owner'], fields(
        inventory, supplier='', invoiceNumber='', lines=[invoice_line(product, quantity=value, unit='kg')])))


def test_normalization_rejects_precision_and_product_overflow(inventory):
    service, product, package = setup(inventory)
    denied('invalid', lambda: service.create(inventory.tokens['owner'], fields(
        inventory, supplier='', invoiceNumber='', lines=[invoice_line(product, quantity='0.000000001', unit='lb')])))
    denied('invalid', lambda: service.create(inventory.tokens['owner'], fields(
        inventory, supplier='', invoiceNumber='', lines=[invoice_line(product, package, quantity='999999999999999')])))


def test_normalization_ignores_representational_trailing_zero_scale(inventory):
    service, product, package = setup(inventory)
    lines = [
        invoice_line(product, package, quantity='2.000000000'),
        invoice_line(product, quantity='2.000000000', unit='kg'),
        invoice_line(product, quantity='2.000000000', unit='lb'),
    ]
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Zeros', invoiceNumber='1', lines=lines))
    assert [line['normalizedQuantity'] for line in draft['lines']] == ['12', '2', '0.90718474']


def test_open_invoice_aggregate_cannot_exceed_stock_domain(inventory):
    service, product, _ = setup(inventory)
    service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Large', invoiceNumber='1',
        lines=[invoice_line(product, quantity='999999999999995', unit='kg')]))
    denied('invalid', lambda: service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Large', invoiceNumber='2',
        lines=[invoice_line(product, quantity='5', unit='kg')])))
    incoming = service.incoming(inventory.tokens['owner'])
    assert incoming['items'][0]['incomingQuantity'] == '999999999999995'


def test_replay_rechecks_current_authority(inventory):
    service, product, _ = setup(inventory)
    body = fields(inventory, supplier='Replay', invoiceNumber='1', lines=[invoice_line(product)])
    service.create(inventory.tokens['owner'], body)
    with inventory.connect() as db:
        db.execute("DELETE FROM business_memberships WHERE user_id=%s", (inventory.users['owner'],))
        db.execute("UPDATE account_store_memberships SET role='crew',capabilities=ARRAY['inventory.view','receipts.draft'] WHERE user_id=%s",
                   (inventory.users['owner'],))
    denied('forbidden', lambda: service.create(inventory.tokens['owner'], body))


def test_measurement_change_requires_unmatch_then_explicit_rematch(inventory):
    service = ReceivingService(inventory.connect, inventory.accounts)
    product = inventory.service.create_product(inventory.tokens['owner'], fields(
        inventory, name='Correctable', sku='CORRECT', baseUnit='kg'))
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Units', invoiceNumber='1', lines=[invoice_line(product, quantity='2', unit='kg')]))
    inventory.service.correct_measurement(inventory.tokens['owner'], product['id'], fields(
        inventory, version=product['version'], baseUnit='g', containerAmount=None, acknowledgeRecipes=True))
    changed = service.invoice(inventory.tokens['owner'], draft['id'])
    assert changed['needsCountReview'] is False and changed['needsCatalogReview'] is True
    assert service.incoming(inventory.tokens['owner'])['items'] == []
    denied('conflict', lambda: service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=draft['version'], supplier='Units', invoiceNumber='1', lines=draft['lines'])))
    raw = {key: draft['lines'][0][key] for key in ('id','description','sku','received')}
    unmatched = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=draft['version'], supplier='Units', invoiceNumber='1',
        lines=[{**raw, 'productId': None, 'packageId': None, 'quantity': None, 'unit': ''}]))
    rematched = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=unmatched['version'], supplier='Units', invoiceNumber='1',
        lines=[{**raw, 'id': str(uuid4()), 'productId': product['id'], 'packageId': None, 'quantity': '2000', 'unit': 'g'}]))
    assert rematched['needsCountReview'] is False and rematched['needsCatalogReview'] is False
    assert rematched['lines'][0]['normalizedQuantity'] == '2000'


def test_combined_product_is_excluded_until_line_is_rematched(inventory):
    service = ReceivingService(inventory.connect, inventory.accounts)
    source = inventory.service.create_product(inventory.tokens['owner'], fields(
        inventory, name='Source Quella', sku='SOURCE-Q', baseUnit='kg', containerAmount='6'))
    target = inventory.service.create_product(inventory.tokens['owner'], fields(
        inventory, name='Canonical Quella', sku='CANONICAL-Q', baseUnit='kg', containerAmount='6'))
    draft = service.create(inventory.tokens['owner'], fields(
        inventory, supplier='Merge', invoiceNumber='1', lines=[invoice_line(source, quantity='2', unit='kg')]))
    source = inventory.service.product(inventory.tokens['owner'], source['id'])
    inventory.service.combine_product(inventory.tokens['owner'], source['id'], fields(
        inventory, targetProductId=target['id'], sourceVersion=source['version'],
        targetVersion=target['version'], confirmed=True))
    changed = service.invoice(inventory.tokens['owner'], draft['id'])
    assert changed['needsCountReview'] is False and changed['needsCatalogReview'] is True
    incoming = service.incoming(inventory.tokens['owner'])
    assert incoming['items'] == [] and incoming['needsCountReview'] is False and incoming['needsCatalogReview'] is True
    raw = {key: draft['lines'][0][key] for key in ('id','description','sku','received')}
    unmatched = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=draft['version'], supplier='Merge', invoiceNumber='1',
        lines=[{**raw, 'productId': None, 'packageId': None, 'quantity': None, 'unit': ''}]))
    recovered = service.edit(inventory.tokens['owner'], draft['id'], fields(
        inventory, version=unmatched['version'], supplier='Merge', invoiceNumber='1',
        lines=[{**raw, 'id': str(uuid4()), 'productId': target['id'], 'packageId': None, 'quantity': '2', 'unit': 'kg'}]))
    assert recovered['needsCountReview'] is False and recovered['needsCatalogReview'] is False
    assert service.incoming(inventory.tokens['owner'])['items'][0]['productId'] == target['id']


def test_upgrade_from_027_adds_invoice_tables_without_rewriting_catalog(empty_database, tmp_path):
    before = tmp_path / 'before-028'
    only_028 = tmp_path / 'only-028'
    before.mkdir(); only_028.mkdir()
    migrations = Path('migrations').resolve()
    for path in migrations.glob('*.sql'):
        if path.name < '028_':
            (before / path.name).symlink_to(path)
    (only_028 / '028_invoice_drafts.sql').symlink_to(migrations / '028_invoice_drafts.sql')
    connect = lambda: psycopg.connect(empty_database)
    migrate(connect, directory=before)
    product_id = str(uuid4())
    with connect() as db:
        business = db.execute("INSERT INTO businesses(name) VALUES('027 preserved') RETURNING id").fetchone()[0]
        store = db.execute("INSERT INTO stores(name,access_code_hash,business_id) VALUES('Kept',repeat('a',64),%s) RETURNING id", (business,)).fetchone()[0]
        db.execute("INSERT INTO inventory_products(id,business_id,sku,name,base_unit) VALUES(%s,%s,'KEEP-027','Kept product','kg')", (product_id,business))
        db.execute("INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,'KEEP-027')", (business,product_id))
        evidence = db.execute('SELECT name,sku,base_unit FROM inventory_products WHERE id=%s', (product_id,)).fetchone()
    assert migrate(connect, directory=only_028) == ['028_invoice_drafts.sql']
    with connect() as db:
        assert db.execute('SELECT name,sku,base_unit FROM inventory_products WHERE id=%s', (product_id,)).fetchone() == evidence
        assert db.execute("SELECT to_regclass('inventory_invoice_drafts'),to_regclass('inventory_invoice_lines')").fetchone() == (
            'inventory_invoice_drafts','inventory_invoice_lines')
        assert db.execute('SELECT name FROM stores WHERE id=%s', (store,)).fetchone()[0] == 'Kept'
