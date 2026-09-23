from concurrent.futures import ThreadPoolExecutor
from threading import Event
from uuid import uuid4

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.identity.accounts_core import policy_lock


def fields(i, **values):
    return {'requestId': str(uuid4()), 'expectedStoreId': i.stores[0], **values}


def create(i, sku='000184', **values):
    return i.service.create_product(i.tokens['owner'], fields(i, name='Vanilla tub', sku=sku, baseUnit='each', **values))


def shelf(i, name='Back freezer'):
    return i.service.create_shelf(i.tokens['manager'], fields(i, name=name))


def test_catalog_shared_between_stores_and_hidden_between_companies(inventory):
    i=inventory; product=create(i)
    assert product['sku']=='000184'
    assert i.service.products(i.second)['items']==[product]
    assert i.service.products(i.tokens['foreign'])['items']==[]
    with pytest.raises(IdentityError) as e: i.service.product(i.tokens['foreign'],product['id'])
    assert e.value.code=='not_found'
    assert i.service.product(i.tokens['crew'],product['id'])==product


@pytest.mark.parametrize('who', ['crew','manager','noinventory'])
def test_local_roles_cannot_manage_shared_catalog(inventory,who):
    i=inventory
    with pytest.raises(IdentityError) as e: i.service.create_product(i.tokens[who],fields(i,name='No',sku='123',baseUnit='each'))
    assert e.value.code=='forbidden'
    assert i.service.products(i.tokens['owner'])['items']==[]


def test_explicit_catalog_delegation_can_create_but_not_create_shelf(inventory):
    i=inventory
    i.service.create_product(i.tokens['delegate'],fields(i,name='Milk',sku='M-01',baseUnit='kg'))
    with pytest.raises(IdentityError): i.service.create_shelf(i.tokens['delegate'],fields(i,name='No'))


@pytest.mark.parametrize('values', [{'sku':123},{'sku':'a b'},{'sku':'x\n'},{'sku':''},{'sku':'x'*65},
                                  {'name':'\u0000bad'},{'name':''},{'baseUnit':'pounds'},{'baseUnit':None}])
def test_product_validation_prevents_partial_records(inventory, values):
    i=inventory; data={'name':'Milk','sku':'001','baseUnit':'kg',**values}
    with pytest.raises(IdentityError) as e: i.service.create_product(i.tokens['owner'],fields(i,**data))
    assert e.value.code=='invalid'
    assert i.service.products(i.tokens['owner'])['items']==[]


def test_sku_change_keeps_identity_and_reserves_previous_aliases_even_when_archived(inventory):
    i=inventory; p=create(i,'Ab-01')
    edited=i.service.edit_product(i.tokens['owner'],p['id'],fields(i,version=p['version'],name='Vanilla renamed',sku='002'))
    assert edited['id']==p['id'] and edited['version']==2
    assert i.service.products(i.second,query='ab-01')['items']==[edited]
    for sku in ('ab-01','002'):
        with pytest.raises(IdentityError) as e: create(i,sku)
        assert e.value.reason=='duplicate_identifier'
    archived=i.service.product_state(i.tokens['owner'],p['id'],fields(i,version=2,active=False))
    assert not archived['active'] and not i.service.products(i.second)['items']
    assert i.service.products(i.second,state='archived')['items']==[archived]
    with pytest.raises(IdentityError): create(i,'AB-01')
    restored=i.service.product_state(i.tokens['owner'],p['id'],fields(i,version=3,active=True))
    assert restored['id']==p['id'] and restored['active']
    with pytest.raises(IdentityError):
        i.service.edit_product(i.tokens['owner'],p['id'],fields(i,version=4,name='Oops',sku='002',baseUnit='kg'))


def test_stale_edit_leaves_current_product_and_audit_unchanged(inventory):
    i=inventory; p=create(i)
    saved=i.service.edit_product(i.tokens['owner'],p['id'],fields(i,version=1,name='Current',sku=p['sku']))
    with pytest.raises(IdentityError) as e:
        i.service.edit_product(i.tokens['owner'],p['id'],fields(i,version=1,name='Stale',sku='999'))
    assert e.value.reason=='stale_record' and i.service.product(i.tokens['owner'],p['id'])==saved
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_changes').fetchone()[0]==2
        assert c.execute("SELECT count(*) FROM inventory_product_skus WHERE sku='999'").fetchone()[0]==0


def test_request_retry_returns_original_result_but_never_reapplies_or_skips_authority(inventory):
    i=inventory; f=fields(i,name='Milk',sku='0001',baseUnit='kg'); token=i.tokens['owner']
    p=i.service.create_product(token,f)
    assert i.service.create_product(token,f)==p
    with pytest.raises(IdentityError) as e: i.service.create_product(token,{**f,'name':'Different'})
    assert e.value.reason=='state_conflict'
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_products').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM inventory_changes').fetchone()[0]==1
    i.accounts.logout(token)
    with pytest.raises(IdentityError) as e: i.service.create_product(token,f)
    assert e.value.code=='unauthenticated'


def test_concurrent_retry_creates_one_product_and_one_change(inventory):
    i=inventory; f=fields(i,name='Milk',sku='M1',baseUnit='kg')
    with ThreadPoolExecutor(max_workers=2) as ex:
        results=list(ex.map(lambda _:i.service.create_product(i.tokens['owner'],f),range(2)))
    assert results[0]==results[1]
    with i.connect() as c: assert c.execute('SELECT count(*) FROM inventory_changes').fetchone()[0]==1


def test_catalog_and_shelf_writes_roll_back_if_audit_fails(inventory,monkeypatch):
    i=inventory
    def fail(*_): raise RuntimeError('audit failure')
    monkeypatch.setattr(i.service.repository,'record',fail)
    with pytest.raises(RuntimeError): create(i)
    with pytest.raises(RuntimeError): shelf(i)
    with i.connect() as c:
        for table in ('inventory_products','inventory_product_skus','inventory_shelves','inventory_requests'):
            assert c.execute(f'SELECT count(*) FROM {table}').fetchone()[0]==0


def test_first_shelf_assignment_reuses_catalog_and_keeps_removal_local(inventory):
    i=inventory; p=create(i); a=shelf(i); b=shelf(i,'Front freezer')
    first=fields(i,version=1,active=True)
    assigned=i.service.place(i.tokens['manager'],a['id'],p['id'],first)
    assert assigned['shelf']['version']==2
    assert i.service.place(i.tokens['manager'],a['id'],p['id'],first)==assigned
    i.service.place(i.tokens['manager'],b['id'],p['id'],fields(i,version=1,active=True))
    again=i.service.place(i.tokens['manager'],a['id'],p['id'],fields(i,version=2,active=True))
    assert again['shelf']['version']==2
    i.service.place(i.tokens['manager'],a['id'],p['id'],fields(i,version=2,active=False))
    assert i.service.shelf(i.tokens['crew'],a['id'])['products']['items']==[]
    assert i.service.shelf(i.tokens['crew'],b['id'])['products']['items']==[p]
    assert i.service.shelves(i.second)['items']==[]
    with i.connect() as c:
        assert c.execute('SELECT count(*) FROM inventory_products').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM inventory_store_products').fetchone()[0]==1
        assert c.execute('SELECT count(*) FROM inventory_shelf_products WHERE active').fetchone()[0]==1


def test_archive_preserves_placement_and_blocks_new_assignment(inventory):
    i=inventory; p=create(i); s=shelf(i); other=shelf(i,'Other shelf')
    i.service.place(i.tokens['manager'],s['id'],p['id'],fields(i,version=1,active=True))
    i.service.product_state(i.tokens['owner'],p['id'],fields(i,version=1,active=False))
    assert not i.service.shelf(i.tokens['crew'],s['id'])['products']['items'][0]['active']
    with pytest.raises(IdentityError) as e: i.service.place(i.tokens['manager'],other['id'],p['id'],fields(i,version=1,active=True))
    assert e.value.reason=='state_conflict'
    i.service.place(i.tokens['manager'],s['id'],p['id'],fields(i,version=2,active=False))


def test_store_and_company_ids_cannot_retarget_inventory_writes(inventory):
    i=inventory; p=create(i); s=shelf(i)
    with pytest.raises(IdentityError) as e:
        i.service.create_product(i.tokens['owner'],fields(i,name='No',sku='no',baseUnit='each',expectedStoreId=i.stores[1]))
    assert e.value.reason=='store_context_changed'
    with pytest.raises(IdentityError): i.service.shelf(i.second,s['id'])
    with pytest.raises(IdentityError): i.service.place(i.tokens['crew'],s['id'],p['id'],fields(i,version=1,active=True))
    with pytest.raises(IdentityError): i.service.shelves(i.tokens['noinventory'])
    foreign=i.service.create_product(i.tokens['foreign'],fields(i,expectedStoreId=i.stores[2],name='Other',sku=p['sku'],baseUnit='each'))
    with pytest.raises(IdentityError): i.service.place(i.tokens['manager'],s['id'],foreign['id'],fields(i,version=1,active=True))
    with pytest.raises(psycopg.errors.ForeignKeyViolation),i.connect() as c:
        c.execute('INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)',(i.companies[0],i.stores[0],foreign['id']))
    with pytest.raises(psycopg.errors.ForeignKeyViolation),i.connect() as c:
        c.execute('INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)',(i.companies[0],i.stores[2],p['id']))


def test_lists_are_bounded_searchable_and_paginate_without_duplicates(inventory):
    i=inventory
    for n in range(43): create(i,f'{n:05d}')
    first=i.service.products(i.tokens['owner']); second=i.service.products(i.tokens['owner'],after=first['nextCursor'])
    assert len(first['items'])==40 and len(second['items'])==3 and second['nextCursor'] is None
    assert len({p['id'] for p in first['items']+second['items']})==43
    assert len(i.service.products(i.tokens['owner'],query='00042')['items'])==1
    assert not i.service.products(i.tokens['owner'],query="%' OR true --")['items']


def test_revocation_committed_while_write_waits_prevents_product_creation(inventory):
    i=inventory; waiting=Event()
    def attempt():
        waiting.set()
        try: i.service.create_product(i.tokens['delegate'],fields(i,name='No',sku='no',baseUnit='each'))
        except IdentityError: return 'denied'
        return 'wrote'
    with ThreadPoolExecutor(max_workers=1) as ex:
        with i.connect() as c:
            policy_lock(c)
            c.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s",(i.users['delegate'],))
            result=ex.submit(attempt); assert waiting.wait(3) and not result.done()
        assert result.result(timeout=5)=='denied'
    assert i.service.products(i.tokens['owner'])['items']==[]


def test_shelf_names_and_stale_changes_are_scoped_and_preserve_placements(inventory):
    i = inventory
    product, first = create(i), shelf(i, 'Back freezer')
    with pytest.raises(IdentityError) as duplicate:
        shelf(i, 'BACK FREEZER')
    assert duplicate.value.reason == 'duplicate_identifier'
    second = i.service.create_shelf(i.second, fields(i, expectedStoreId=i.stores[1], name='Back freezer'))
    assert second['id'] != first['id']
    i.service.place(i.tokens['manager'], first['id'], product['id'], fields(i, version=1, active=True))
    for change in (
        lambda: i.service.edit_shelf(i.tokens['manager'], first['id'], fields(i, version=1, name='Stale name')),
        lambda: i.service.place(i.tokens['manager'], first['id'], product['id'], fields(i, version=1, active=False)),
    ):
        with pytest.raises(IdentityError) as stale:
            change()
        assert stale.value.reason == 'stale_record'
    current = i.service.shelf(i.tokens['manager'], first['id'])
    assert current['name'] == 'Back freezer' and current['products']['items'] == [product]


def test_database_rejects_cross_store_placement_even_with_valid_local_listing(inventory):
    i = inventory
    product, first = create(i), shelf(i)
    with i.connect() as connection:
        connection.execute('INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)',
                           (i.companies[0], i.stores[1], product['id']))
    with pytest.raises(psycopg.errors.ForeignKeyViolation), i.connect() as connection:
        connection.execute('INSERT INTO inventory_shelf_products(business_id,store_id,shelf_id,product_id) VALUES(%s,%s,%s,%s)',
                           (i.companies[0], i.stores[1], first['id'], product['id']))
