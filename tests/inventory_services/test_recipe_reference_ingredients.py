from uuid import uuid4

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production.service import ProductionService
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate


def fields(i,**values):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**values}


def denied(code,operation):
    with pytest.raises(IdentityError) as caught:
        operation()
    assert caught.value.code==code


def tracked_stock(i,amount='20'):
    product=i.service.create_product(i.tokens['owner'],fields(i,name='Tracked water',sku='TRACK-WATER',baseUnit='kg'))
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-10-20'))
    line=i.counts.lines(i.tokens['owner'],count['id'])['items'][0]
    saved=i.counts.save(i.tokens['owner'],count['id'],line['id'],fields(
        i,version=line['version'],entry={'mode':'total','amount':amount,'unit':'kg'}))
    reviewed=i.counts.transition(i.tokens['owner'],count['id'],'review',fields(i,version=saved['count']['version']))
    i.counts.transition(i.tokens['owner'],count['id'],'post',fields(i,version=reviewed['version']))
    return product


def recipe_fields(i,ingredients,references,**values):
    return fields(i,name='Lampone',yieldAmount='1',yieldUnit='batch',instructions='Blend.',
                  ingredients=ingredients,referenceIngredients=references,**values)


def production_fields(i,recipe):
    return fields(i,logId=str(uuid4()),confirmed=True,businessDate='2026-10-21',
                  entries=[{'recipeId':recipe['id'],'revisionId':recipe['revisionId'],'batches':1}])


def test_mixed_reference_ingredients_render_but_only_tracked_stock_moves(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); tracked=tracked_stock(i)
    with i.connect() as db:
        catalog_before=db.execute('SELECT count(*) FROM inventory_products').fetchone()[0]
        lines_before=db.execute('SELECT count(*) FROM inventory_count_lines').fetchone()[0]
    made=service.create_recipe(i.tokens['owner'],recipe_fields(i,
        [{'productId':tracked['id'],'amount':'1','unit':'kg'}],
        [{'name':'Water','amount':'0.5','unit':'kg'},
         {'name':'Raspberries','amount':'250','unit':'g'}]))
    assert made['referenceIngredients']==[
        {'name':'Water','amount':'0.5','unit':'kg'},
        {'name':'Raspberries','amount':'250','unit':'g'}]
    preview=service.preview(i.tokens['owner'],{'businessDate':'2026-10-21','entries':[
        {'recipeId':made['id'],'revisionId':made['revisionId'],'batches':1}]})
    assert preview['canConfirm'] is True
    assert [(d['productId'],d['recipeAmount'],d['allowanceAmount'],d['quantity']) for d in preview['deductions']]==[
        (tracked['id'],'1','0.01','1.01')]
    confirmed=service.confirm(i.tokens['owner'],production_fields(i,made))
    assert len(confirmed['ingredients'])==1 and confirmed['ingredients'][0]['productId']==tracked['id']
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='18.99'
    reversed_log=service.reverse(i.tokens['owner'],confirmed['id'],fields(i,reason='Test reversal'))
    assert reversed_log['state']=='reversed'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='20'
    with i.connect() as db:
        assert db.execute('SELECT count(*) FROM inventory_products').fetchone()[0]==catalog_before
        assert db.execute('SELECT count(*) FROM inventory_count_lines').fetchone()[0]==lines_before
        assert db.execute("SELECT count(*) FROM inventory_stock_movements WHERE kind IN ('production','reversal')").fetchone()[0]==2


def test_reference_only_recipe_records_and_reverses_without_inventory_evidence(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts)
    made=service.create_recipe(i.tokens['owner'],recipe_fields(i,[],[
        {'name':'Water','amount':'1','unit':'kg'},
        {'name':'Raspberries','amount':'200','unit':'g'}]))
    preview=service.preview(i.tokens['owner'],{'businessDate':'2026-10-21','entries':[
        {'recipeId':made['id'],'revisionId':made['revisionId'],'batches':3}]})
    assert preview['canConfirm'] is True and preview['deductions']==[] and preview['issues']==[]
    confirmed=service.confirm(i.tokens['owner'],production_fields(i,made))
    assert confirmed['ingredients']==[]
    assert service.reverse(i.tokens['owner'],confirmed['id'],fields(i,reason='No stock to restore'))['state']=='reversed'
    with i.connect() as db:
        assert db.execute("SELECT count(*) FROM inventory_stock_movements WHERE kind IN ('production','reversal')").fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM inventory_products').fetchone()==(0,)


def test_reference_edits_are_explicit_revisioned_and_sealed(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts)
    made=service.create_recipe(i.tokens['owner'],recipe_fields(i,[],[
        {'name':'Water','amount':'1','unit':'kg'}]))
    omitted=fields(i,version=made['version'],name='Lampone 2',yieldAmount='1',yieldUnit='batch',
                   instructions='',ingredients=[])
    denied('invalid',lambda:service.edit_recipe(i.tokens['owner'],made['id'],omitted))
    edited=service.edit_recipe(i.tokens['owner'],made['id'],recipe_fields(
        i,[],[{'name':'Water','amount':'2','unit':'kg'}],version=made['version']))
    assert edited['version']==2 and edited['referenceIngredients'][0]['amount']=='2'
    with pytest.raises(psycopg.errors.CheckViolation),i.connect() as db:
        db.execute("UPDATE production_recipe_revisions SET reference_ingredients='[]' WHERE id=%s",(made['revisionId'],))
    cleared=service.edit_recipe(i.tokens['owner'],made['id'],recipe_fields(
        i,[{'productId':tracked_stock(i)['id'],'amount':'1','unit':'kg'}],[],version=edited['version']))
    assert cleared['referenceIngredients']==[]


def test_null_references_and_empty_omitted_edit_are_validation_errors(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); tracked=tracked_stock(i)
    denied('invalid',lambda:service.create_recipe(i.tokens['owner'],recipe_fields(
        i,[{'productId':tracked['id'],'amount':'1','unit':'kg'}],None)))
    made=service.create_recipe(i.tokens['owner'],fields(
        i,name='Legacy shape',yieldAmount='1',yieldUnit='batch',instructions='',
        ingredients=[{'productId':tracked['id'],'amount':'1','unit':'kg'}]))
    denied('invalid',lambda:service.edit_recipe(i.tokens['owner'],made['id'],fields(
        i,version=made['version'],name='Null edit',yieldAmount='1',yieldUnit='batch',instructions='',
        ingredients=[{'productId':tracked['id'],'amount':'1','unit':'kg'}],referenceIngredients=None)))
    denied('invalid',lambda:service.edit_recipe(i.tokens['owner'],made['id'],fields(
        i,version=made['version'],name='Empty edit',yieldAmount='1',yieldUnit='batch',instructions='',ingredients=[])))


def test_reference_validation_permissions_and_mapped_products_remain_strict(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); tracked=tracked_stock(i)
    denied('forbidden',lambda:service.create_recipe(i.tokens['crew'],recipe_fields(
        i,[],[{'name':'Water','amount':'1','unit':'kg'}])))
    denied('conflict',lambda:service.create_recipe(i.tokens['owner'],recipe_fields(
        i,[{'productId':str(uuid4()),'amount':'1','unit':'kg'}],[])))
    current=i.service.product(i.tokens['owner'],tracked['id'])
    i.service.product_state(i.tokens['owner'],tracked['id'],fields(i,version=current['version'],active=False))
    denied('conflict',lambda:service.create_recipe(i.tokens['owner'],recipe_fields(
        i,[{'productId':tracked['id'],'amount':'1','unit':'kg'}],[])))


@pytest.mark.parametrize('references',[
    {}, [None], [{'name':'Water','amount':'1','unit':'kg','productId':'unexpected'}],
    [{'name':'Bad\x00name','amount':'1','unit':'kg'}],
    [{'name':'Water','amount':'0','unit':'kg'}],
    [{'name':'Water','amount':'1.5','unit':'each'}],
    [{'name':'Water','amount':'1','unit':'ml'}],
    [{'name':'Water','amount':'1','unit':'kg'},{'name':' water ','amount':'2','unit':'kg'}],
])
def test_invalid_reference_shapes_are_rejected(inventory,references):
    service=ProductionService(inventory.connect,inventory.accounts)
    denied('invalid',lambda:service.create_recipe(inventory.tokens['owner'],recipe_fields(inventory,[],references)))


def test_combined_ingredient_limit_and_cross_duplicate_name(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); tracked=tracked_stock(i)
    references=[{'name':f'Reference {n}','amount':'1','unit':'kg'} for n in range(50)]
    denied('invalid',lambda:service.create_recipe(i.tokens['owner'],recipe_fields(
        i,[{'productId':tracked['id'],'amount':'1','unit':'kg'}],references)))
    denied('invalid',lambda:service.create_recipe(i.tokens['owner'],recipe_fields(
        i,[{'productId':tracked['id'],'amount':'1','unit':'kg'}],
        [{'name':' tracked water ','amount':'1','unit':'kg'}])))


def test_upgrade_026_preserves_populated_recipe_and_production_evidence(empty_database,tmp_path):
    before_026=tmp_path/'before-026'; before_026.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        if path.name<'026_': (before_026/path.name).symlink_to(path.resolve())
    connect=lambda:psycopg.connect(empty_database)
    migrate(connect,directory=before_026)
    product_id,recipe_id,revision_id,log_id=(str(uuid4()) for _ in range(4))
    with connect() as db:
        business=db.execute("INSERT INTO businesses(name) VALUES('Recipe upgrade') RETURNING id").fetchone()[0]
        store=db.execute("INSERT INTO stores(name,access_code_hash,business_id) VALUES('Store',repeat('a',64),%s) RETURNING id",(business,)).fetchone()[0]
        user=db.execute("""INSERT INTO account_users(username,display_name,password_salt,password_hash)
            VALUES('recipe-upgrade','Owner','salt','hash') RETURNING id""").fetchone()[0]
        db.execute("INSERT INTO inventory_products(id,business_id,sku,name,base_unit) VALUES(%s,%s,'RECIPE-OLD','Old ingredient','kg')",(product_id,business))
        db.execute("INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,'RECIPE-OLD')",(business,product_id))
        db.execute("INSERT INTO production_recipes(id,business_id,current_revision_id,created_by) VALUES(%s,%s,NULL,%s)",(recipe_id,business,user))
        db.execute("""INSERT INTO production_recipe_revisions
            (id,business_id,recipe_id,revision_number,name,yield_amount,yield_unit,instructions,created_by)
            VALUES(%s,%s,%s,1,'Existing recipe',1,'batch','Keep me',%s)""",(revision_id,business,recipe_id,user))
        db.execute("""INSERT INTO production_recipe_ingredients
            (business_id,recipe_id,revision_id,product_id,name,sku,amount,unit,base_unit,base_amount)
            VALUES(%s,%s,%s,%s,'Old ingredient','RECIPE-OLD',1,'kg','kg',1)""",
                   (business,recipe_id,revision_id,product_id))
        db.execute("UPDATE production_recipe_revisions SET sealed=true WHERE id=%s",(revision_id,))
        db.execute("UPDATE production_recipes SET current_revision_id=%s WHERE id=%s",(revision_id,recipe_id))
        db.execute("""INSERT INTO production_logs
            (id,business_id,store_id,business_date,state,payload_fingerprint,created_by,creator_name)
            VALUES(%s,%s,%s,'2026-10-21','building',%s,%s,'Owner')""",(log_id,business,store,'a'*64,user))
        db.execute("""INSERT INTO production_log_entries
            (business_id,store_id,log_id,sequence,recipe_id,revision_id,name,yield_amount,yield_unit,batches)
            VALUES(%s,%s,%s,0,%s,%s,'Existing recipe',1,'batch',2)""",
                   (business,store,log_id,recipe_id,revision_id))
        db.execute("UPDATE production_logs SET state='confirmed' WHERE id=%s",(log_id,))
        evidence={table:db.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall() for table in (
            'production_recipes','production_recipe_revisions','production_recipe_ingredients',
            'production_logs','production_log_entries')}
    only_026=tmp_path/'only-026'; only_026.mkdir()
    (only_026/'026_recipe_reference_ingredients.sql').symlink_to(
        (MIGRATIONS/'026_recipe_reference_ingredients.sql').resolve())
    assert migrate(connect,directory=only_026)==['026_recipe_reference_ingredients.sql']
    with connect() as db:
        assert db.execute('SELECT reference_ingredients FROM production_recipe_revisions WHERE id=%s',(revision_id,)).fetchone()==([] ,)
        for table,rows in evidence.items():
            upgraded=db.execute(f'SELECT * FROM {table} ORDER BY 1').fetchall()
            if table=='production_recipe_revisions':
                upgraded=[row[:-1] for row in upgraded]
            assert upgraded==rows
    with pytest.raises(psycopg.errors.CheckViolation),connect() as db:
        db.execute("UPDATE production_recipe_revisions SET reference_ingredients='[]' WHERE id=%s",(revision_id,))
    assert migrate(connect,directory=only_026)==[]
