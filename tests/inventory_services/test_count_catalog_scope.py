from uuid import uuid4

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate


def fields(i, store=None, **values):
    return {'requestId':str(uuid4()),'expectedStoreId':store or i.stores[0],**values}


def product(i, name, sku, token=None, store=None):
    return i.service.create_product(token or i.tokens['owner'],fields(i,store,name=name,sku=sku,baseUnit='kg'))


def save_zero(i, token, count, line, store=None):
    return i.counts.save(token,count['id'],line['id'],fields(i,store,version=line['version'],entry={'mode':'total','amount':'0','unit':'kg'}))


def denied(code, operation):
    with pytest.raises(IdentityError) as caught:
        operation()
    assert caught.value.code == code


def test_count_starts_from_full_active_business_catalog_and_materializes_store_listing(inventory):
    i=inventory
    kept=product(i,'Never shelved','CAT-KEEP')
    inactive_listing=product(i,'Inactive listing','CAT-INACTIVE')
    archived=product(i,'Archived','CAT-OLD')
    i.service.product_state(i.tokens['owner'],archived['id'],fields(i,version=archived['version'],active=False))
    foreign=i.service.create_product(i.tokens['foreign'],fields(i,i.stores[2],name='Foreign',sku='CAT-FOREIGN',baseUnit='kg'))
    with i.connect() as db:
        db.execute('DELETE FROM inventory_store_products WHERE business_id=%s AND store_id=%s AND product_id=%s',
                   (i.companies[0],i.stores[0],kept['id']))
        db.execute('''INSERT INTO inventory_store_products(business_id,store_id,product_id,active)
            VALUES(%s,%s,%s,false) ON CONFLICT(business_id,store_id,product_id)
            DO UPDATE SET active=false''',(i.companies[0],i.stores[0],inactive_listing['id']))
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-25'))
    lines=i.counts.lines(i.tokens['owner'],count['id'])['items']
    assert {(line['name'],line['shelfId']) for line in lines} == {('Never shelved',None),('Inactive listing',None)}
    with i.connect() as db:
        assert db.execute('SELECT count(*) FROM inventory_store_products WHERE store_id=%s AND active AND product_id=ANY(%s::uuid[])',
                          (i.stores[0],[kept['id'],inactive_listing['id']])).fetchone()[0] == 2
    assert all(line['productId'] != archived['id'] for line in lines)
    assert all(line['productId'] != foreign['id'] for line in lines)


def test_other_store_quantity_never_becomes_the_new_store_baseline(inventory):
    i=inventory
    p=product(i,'Shared catalog','CAT-SHARED')
    second=i.counts.start(i.second,fields(i,i.stores[1],businessDate='2026-09-25'))
    second_line=i.counts.lines(i.second,second['id'])['items'][0]
    saved=i.counts.save(i.second,second['id'],second_line['id'],fields(i,i.stores[1],version=1,entry={'mode':'total','amount':'9','unit':'kg'}))
    reviewed=i.counts.transition(i.second,second['id'],'review',fields(i,i.stores[1],version=saved['count']['version']))
    i.counts.transition(i.second,second['id'],'post',fields(i,i.stores[1],version=reviewed['version']))
    first=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-25'))
    comparison=i.counts.comparisons(i.tokens['owner'],first['id'])['items'][0]
    assert comparison['productId']==p['id'] and comparison['previousQuantity'] is None
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None


def test_legacy_draft_append_preserves_existing_evidence_and_is_idempotent(inventory,monkeypatch):
    i=inventory
    original=product(i,'Original','CAT-ORIGINAL')
    added=product(i,'Added later','CAT-ADDED')
    repository=i.counts.repository
    live_scope=repository.scope
    with monkeypatch.context() as patch:
        patch.setattr(repository,'scope',lambda connection,actor: [row for row in live_scope(connection,actor) if str(row['product_id'])==original['id']])
        count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-25'))
    line=i.counts.lines(i.tokens['owner'],count['id'])['items'][0]
    saved=save_zero(i,i.tokens['owner'],count,line)
    detail=i.counts.detail(i.tokens['owner'],count['id'])
    assert detail['configurationChanged'] is True and detail['catalogProductsAvailable'] is True
    with i.connect() as db:
        before=db.execute('''SELECT l.id,l.version,l.quantity,l.entry,l.observed_by,l.observed_at,
            p.previous_quantity,p.previous_count_id,p.previous_stock_version
            FROM inventory_count_lines l JOIN inventory_count_products p USING(count_id,product_id)
            WHERE l.count_id=%s AND l.product_id=%s''',(count['id'],original['id'])).fetchone()
    body=fields(i,version=saved['count']['version'])
    result=i.counts.include_catalog(i.tokens['owner'],count['id'],body)
    assert result['addedProducts']==1 and result['addedLines']==1
    assert result['configurationChanged'] is False and result['catalogProductsAvailable'] is False
    assert i.counts.include_catalog(i.tokens['owner'],count['id'],body)==result
    endpoint=i.client.post(f"/api/mobile/inventory/counts/{count['id']}/include-catalog",
                           headers={'Authorization':'Bearer '+i.tokens['owner']},json=fields(i,version=result['version']))
    assert endpoint.status_code==200 and endpoint.json()['addedProducts']==0
    with i.connect() as db:
        after=db.execute('''SELECT l.id,l.version,l.quantity,l.entry,l.observed_by,l.observed_at,
            p.previous_quantity,p.previous_count_id,p.previous_stock_version
            FROM inventory_count_lines l JOIN inventory_count_products p USING(count_id,product_id)
            WHERE l.count_id=%s AND l.product_id=%s''',(count['id'],original['id'])).fetchone()
    assert after==before
    appended=[item for item in i.counts.lines(i.tokens['owner'],count['id'])['items'] if item['productId']==added['id']]
    assert len(appended)==1 and appended[0]['quantity'] is None
    denied('conflict',lambda:i.counts.transition(i.tokens['owner'],count['id'],'review',fields(i,version=result['version'])))


def test_catalog_append_rejects_mutated_scope_wrong_access_and_closed_history(inventory,monkeypatch):
    i=inventory
    original=product(i,'Original','CAT-MUTATE')
    product(i,'Added later','CAT-NEW')
    repository=i.counts.repository; live_scope=repository.scope
    with monkeypatch.context() as patch:
        patch.setattr(repository,'scope',lambda connection,actor: [row for row in live_scope(connection,actor) if str(row['product_id'])==original['id']])
        count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-25'))
    i.service.edit_product(i.tokens['owner'],original['id'],fields(i,name='Mutated',sku='CAT-MUTATED',version=original['version']))
    assert i.counts.detail(i.tokens['owner'],count['id'])['catalogProductsAvailable'] is False
    denied('conflict',lambda:i.counts.include_catalog(i.tokens['owner'],count['id'],fields(i,version=count['version'])))
    denied('forbidden',lambda:i.counts.include_catalog(i.tokens['crew'],count['id'],fields(i,version=count['version'])))
    denied('not_found',lambda:i.counts.include_catalog(i.second,count['id'],fields(i,i.stores[1],version=count['version'])))
    cancelled=i.counts.transition(i.tokens['owner'],count['id'],'cancel',fields(i,version=count['version']))
    denied('conflict',lambda:i.counts.include_catalog(i.tokens['owner'],count['id'],fields(i,version=cancelled['version'])))
    with pytest.raises(psycopg.errors.CheckViolation),i.connect() as db:
        db.execute("UPDATE inventory_counts SET configuration_hash=%s WHERE id=%s",('0'*64,count['id']))


def test_include_catalog_rejects_stale_version_and_review_count(inventory):
    i=inventory
    product(i,'Complete catalog','CAT-COMPLETE')
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-25'))
    line=i.counts.lines(i.tokens['owner'],count['id'])['items'][0]
    saved=save_zero(i,i.tokens['owner'],count,line)
    denied('conflict',lambda:i.counts.include_catalog(
        i.tokens['owner'],count['id'],fields(i,version=count['version'])))
    reviewed=i.counts.transition(i.tokens['owner'],count['id'],'review',
                                  fields(i,version=saved['count']['version']))
    denied('conflict',lambda:i.counts.include_catalog(
        i.tokens['owner'],count['id'],fields(i,version=reviewed['version'])))


def test_upgrade_025_preserves_populated_count_evidence_and_tightly_guards_hash_changes(
        empty_database,tmp_path):
    before_025=tmp_path/'before-025'
    before_025.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        if path.name<'025_':
            (before_025/path.name).symlink_to(path.resolve())
    connect=lambda:psycopg.connect(empty_database)
    migrate(connect,directory=before_025)
    product_id,posted_id,draft_id,movement_id=(str(uuid4()) for _ in range(4))
    with connect() as db:
        business=db.execute("INSERT INTO businesses(name) VALUES('025 upgrade') RETURNING id").fetchone()[0]
        store=db.execute("""INSERT INTO stores(name,access_code_hash,business_id)
            VALUES('Upgrade store',repeat('a',64),%s) RETURNING id""",(business,)).fetchone()[0]
        other_store=db.execute("""INSERT INTO stores(name,access_code_hash,business_id)
            VALUES('Other store',repeat('b',64),%s) RETURNING id""",(business,)).fetchone()[0]
        user=db.execute("""INSERT INTO account_users(username,display_name,password_salt,password_hash)
            VALUES('upgrade-025','Owner','salt','hash') RETURNING id""").fetchone()[0]
        db.execute("""INSERT INTO inventory_products(id,business_id,sku,name,base_unit)
            VALUES(%s,%s,'UP-025','Existing product','kg')""",(product_id,business))
        db.execute("INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,'UP-025')",
                   (business,product_id))
        db.execute("INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)",
                   (business,store,product_id))
        db.execute("""INSERT INTO inventory_counts
            (id,business_id,store_id,business_date,configuration_hash,started_by)
            VALUES(%s,%s,%s,'2026-10-20',%s,%s)""",(posted_id,business,store,'a'*64,user))
        db.execute("""INSERT INTO inventory_count_products
            (business_id,store_id,count_id,product_id,name,sku,base_unit,product_version)
            VALUES(%s,%s,%s,%s,'Existing product','UP-025','kg',1)""",
                   (business,store,posted_id,product_id))
        db.execute("""INSERT INTO inventory_count_lines
            (id,business_id,store_id,count_id,product_id,shelf_name,quantity,entry,observed_by,observed_at)
            VALUES(%s,%s,%s,%s,%s,'Not assigned',5,'{"mode":"total","amount":"5","unit":"kg"}',%s,NOW())""",
                   (str(uuid4()),business,store,posted_id,product_id,user))
        db.execute("UPDATE inventory_counts SET state='review',version=2 WHERE id=%s",(posted_id,))
        db.execute("""INSERT INTO inventory_stock_postings
            (business_id,store_id,count_id,product_id,quantity_before,quantity_after,posted_by)
            VALUES(%s,%s,%s,%s,NULL,5,%s)""",(business,store,posted_id,product_id,user))
        db.execute("""INSERT INTO inventory_stock_movements
            (id,business_id,store_id,product_id,base_unit,kind,source_id,quantity_before,quantity_after,version,actor_user_id)
            VALUES(%s,%s,%s,%s,'kg','opening',%s,NULL,5,1,%s)""",
                   (movement_id,business,store,product_id,posted_id,user))
        db.execute("UPDATE inventory_counts SET state='posted',version=3,posted_by=%s,posted_at=NOW() WHERE id=%s",
                   (user,posted_id))
        db.execute("""INSERT INTO inventory_stock_balances
            (business_id,store_id,product_id,count_id,quantity,base_unit,counted_on,version,last_movement_id,last_counted_at)
            VALUES(%s,%s,%s,%s,5,'kg','2026-10-20',1,%s,NOW())""",
                   (business,store,product_id,posted_id,movement_id))
        db.execute("""INSERT INTO inventory_counts
            (id,business_id,store_id,business_date,configuration_hash,started_by)
            VALUES(%s,%s,%s,'2026-10-21',%s,%s)""",(draft_id,business,store,'b'*64,user))
        db.execute("""INSERT INTO inventory_count_products
            (business_id,store_id,count_id,product_id,name,sku,base_unit,product_version,
             previous_quantity,previous_count_id,previous_stock_version)
            VALUES(%s,%s,%s,%s,'Existing product','UP-025','kg',1,5,%s,1)""",
                   (business,store,draft_id,product_id,posted_id))
        db.execute("""INSERT INTO inventory_count_lines
            (id,business_id,store_id,count_id,product_id,shelf_name,quantity,entry,observed_by,observed_at)
            VALUES(%s,%s,%s,%s,%s,'Not assigned',4,'{"mode":"total","amount":"4","unit":"kg"}',%s,NOW())""",
                   (str(uuid4()),business,store,draft_id,product_id,user))
        evidence={table:db.execute(f'SELECT * FROM {table} ORDER BY 1,2,3').fetchall()
                  for table in ('inventory_counts','inventory_count_products','inventory_count_lines',
                                'inventory_stock_postings','inventory_stock_balances')}
    assert migrate(connect)==[path.name for path in sorted(MIGRATIONS.glob('*.sql')) if path.name>='025_']
    with connect() as db:
        for table,rows in evidence.items():
            assert db.execute(f'SELECT * FROM {table} ORDER BY 1,2,3').fetchall()==rows
    assert migrate(connect)==[]
    with connect() as db:
        db.execute("UPDATE inventory_counts SET configuration_hash=%s,version=version+1 WHERE id=%s",
                   ('c'*64,draft_id))
        assert db.execute('SELECT configuration_hash,version FROM inventory_counts WHERE id=%s',
                          (draft_id,)).fetchone()==('c'*64,2)
    for statement,params in (
        ("UPDATE inventory_counts SET store_id=%s WHERE id=%s",(other_store,draft_id)),
        ("UPDATE inventory_counts SET configuration_hash=%s WHERE id=%s",('d'*64,draft_id)),
    ):
        with pytest.raises(psycopg.errors.CheckViolation),connect() as db:
            db.execute(statement,params)
    with connect() as db:
        db.execute("UPDATE inventory_counts SET state='review',version=version+1 WHERE id=%s",(draft_id,))
    with pytest.raises(psycopg.errors.CheckViolation),connect() as db:
        db.execute("UPDATE inventory_counts SET configuration_hash=%s,version=version+1 WHERE id=%s",
                   ('e'*64,draft_id))
    with connect() as db:
        db.execute("UPDATE inventory_counts SET state='cancelled',version=version+1 WHERE id=%s",(draft_id,))
    for count_id in (draft_id,posted_id):
        with pytest.raises(psycopg.errors.CheckViolation),connect() as db:
            db.execute("UPDATE inventory_counts SET configuration_hash=%s WHERE id=%s",('f'*64,count_id))
