from decimal import Decimal
from uuid import uuid4

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.movements import MovementRepository, bounded
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate
from test_counts import fields, setup_stock, start, observe_all, post, denied


def test_production_and_reversal_do_not_erase_count_provenance_or_stale_baseline(inventory):
    i=inventory; product,_=setup_stock(i)
    opening=post(i,observe_all(i,start(i),amount='10'))
    stale=observe_all(i,start(i),amount='8')
    movement=MovementRepository()
    with i.connect() as db:
        actor=i.accounts.require_selected_store(i.tokens['owner'],'production.submit',connection=db,expected_store_id=i.stores[0])
        movement.lock_store(db,actor)
        mid=movement.apply(db,actor,product_id=product['id'],base_unit='kg',quantity_after=Decimal('8.99'),kind='production',source_id=str(uuid4()))
    stock=i.counts.stock_detail(i.tokens['owner'],product['id'])
    assert stock['quantity']=='8.99' and stock['countId']==opening['id'] and stock['stockVersion']==2
    assert stock['lastMovement']=='production' and stock['locations']['items'][0]['quantity']=='10'
    with i.connect() as db:
        actor=i.accounts.require_selected_store(i.tokens['owner'],'production.manage',connection=db,expected_store_id=i.stores[0])
        movement.lock_store(db,actor)
        movement.apply(db,actor,product_id=product['id'],base_unit='kg',quantity_after=Decimal('10'),kind='reversal',source_id=str(uuid4()),reverses_id=mid)
    # Quantity and last count now match the old snapshot; the version must still catch it.
    denied('conflict',lambda:i.counts.transition(i.tokens['owner'],stale['id'],'review',fields(i,version=stale['version'])))
    i.counts.transition(i.tokens['owner'],stale['id'],'cancel',fields(i,version=stale['version']))
    final=post(i,observe_all(i,start(i),amount='9'))
    stock=i.counts.stock_detail(i.tokens['owner'],product['id'])
    assert stock['countId']==final['id'] and stock['quantity']=='9' and stock['stockVersion']==4
    with i.connect() as db:
        assert db.execute('SELECT sum(delta) FROM inventory_stock_movements WHERE product_id=%s',(product['id'],)).fetchone()[0]==Decimal('9')
    with pytest.raises(psycopg.errors.CheckViolation):
        with i.connect() as db:
            db.execute('DELETE FROM inventory_stock_movements WHERE id=%s',(mid,))


def test_movement_precision_never_silently_rounds():
    assert bounded(Decimal('0.0000000010'))==Decimal('0.000000001')
    assert bounded(Decimal('999999999999999.999999999'))==Decimal('999999999999999.999999999')
    for value in ('0.0000000001','-1','NaN','Infinity','1000000000000000'):
        with pytest.raises(IdentityError): bounded(Decimal(value))


def test_upgrade_backfills_counts_and_retains_original_evidence(empty_database,tmp_path):
    connect=lambda:psycopg.connect(empty_database)
    for file in MIGRATIONS.glob('*.sql'):
        if file.name<'018_': (tmp_path/file.name).write_text(file.read_text())
    migrate(connect,directory=tmp_path)
    product,draft=[str(uuid4()) for _ in range(2)]
    count1='00000000-0000-4000-8000-000000000002'
    count2='00000000-0000-4000-8000-000000000001'
    with connect() as db:
        company=db.execute("INSERT INTO businesses(name) VALUES('Upgrade production') RETURNING id").fetchone()[0]
        store=db.execute("INSERT INTO stores(name,access_code_hash,business_id) VALUES('Store','upgrade',%s) RETURNING id",(company,)).fetchone()[0]
        user=db.execute("INSERT INTO account_users(username,display_name,password_salt,password_hash) VALUES('Stock upgrade','Test','salt','hash') RETURNING id").fetchone()[0]
        db.execute("INSERT INTO inventory_products(id,business_id,sku,name,base_unit,container_amount) VALUES(%s,%s,'000123','Ingredient','kg',6)",(product,company))
        db.execute("INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,'000123')",(company,product))
        db.execute('INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)',(company,store,product))
        for cid,previous,previous_id,total,day in ((count1,None,None,Decimal('13.25'),'2026-09-20'),(count2,Decimal('13.25'),count1,Decimal('12.5'),'2026-09-21'),(draft,Decimal('12.5'),count2,None,'2026-09-22')):
            db.execute("INSERT INTO inventory_counts(id,business_id,store_id,business_date,configuration_hash,started_by) VALUES(%s,%s,%s,%s,%s,%s)",(cid,company,store,day,'a'*64,user))
            db.execute("INSERT INTO inventory_count_products(business_id,store_id,count_id,product_id,name,sku,base_unit,product_version,previous_quantity,previous_count_id) VALUES(%s,%s,%s,%s,'Ingredient','000123','kg',1,%s,%s)",(company,store,cid,product,previous,previous_id))
            if total is not None:
                db.execute("UPDATE inventory_counts SET state='review' WHERE id=%s",(cid,))
                db.execute('INSERT INTO inventory_stock_postings(business_id,store_id,count_id,product_id,quantity_before,quantity_after,posted_by,posted_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s)',(company,store,cid,product,previous,total,user,'2026-09-21'))
                db.execute("UPDATE inventory_counts SET state='posted',posted_by=%s,posted_at=%s WHERE id=%s",(user,day,cid))
        db.execute("INSERT INTO inventory_stock_balances(business_id,store_id,product_id,count_id,quantity,base_unit,counted_on) VALUES(%s,%s,%s,%s,12.5,'kg','2026-09-21')",(company,store,product,count2))
        evidence=db.execute('SELECT * FROM inventory_stock_postings ORDER BY count_id').fetchall()
        balances=db.execute('SELECT * FROM inventory_stock_balances').fetchall()
    migrate(connect)
    with connect() as db:
        assert db.execute('SELECT * FROM inventory_stock_postings ORDER BY count_id').fetchall()==evidence
        assert [r[:len(balances[0])] for r in db.execute('SELECT * FROM inventory_stock_balances').fetchall()]==balances
        assert db.execute('SELECT kind,quantity_before,quantity_after,version FROM inventory_stock_movements ORDER BY version').fetchall()==[('opening',None,Decimal('13.25'),1),('count',Decimal('13.25'),Decimal('12.5'),2)]
        assert db.execute('SELECT previous_stock_version FROM inventory_count_products WHERE count_id=%s',(draft,)).fetchone()==(2,)
        assert db.execute('SELECT version FROM inventory_stock_balances').fetchone()==(2,)
    with pytest.raises(psycopg.errors.CheckViolation):
        with connect() as db:
            db.execute('UPDATE inventory_count_products SET previous_quantity=0 WHERE count_id=%s',(draft,))
