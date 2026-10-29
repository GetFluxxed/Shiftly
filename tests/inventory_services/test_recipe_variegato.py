from uuid import uuid4
from decimal import Decimal

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production.service import ProductionService
from backend.shiftly.production import validation as valid
from backend.shiftly.runtime.migrate import MIGRATIONS, migrate


def fields(i,**values):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**values}


def denied(code,operation):
    with pytest.raises(IdentityError) as caught:
        operation()
    assert caught.value.code==code


def stock(i,amount='20'):
    product=i.service.create_product(i.tokens['owner'],fields(
        i,name='Cocoa Crumbolé',sku='COCOA-CRUMBOLE',baseUnit='kg'))
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-10-20'))
    line=i.counts.lines(i.tokens['owner'],count['id'])['items'][0]
    saved=i.counts.save(i.tokens['owner'],count['id'],line['id'],fields(
        i,version=line['version'],entry={'mode':'total','amount':amount,'unit':'kg'}))
    reviewed=i.counts.transition(i.tokens['owner'],count['id'],'review',fields(
        i,version=saved['count']['version']))
    i.counts.transition(i.tokens['owner'],count['id'],'post',fields(i,version=reviewed['version']))
    return product


def test_same_product_in_base_and_variegato_is_preserved_and_aggregated_once(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); cocoa=stock(i)
    made=service.create_recipe(i.tokens['owner'],fields(
        i,name='Tiramisu',yieldAmount='1',yieldUnit='tray',instructions='',
        ingredients=[
            {'productId':cocoa['id'],'amount':'0.300','unit':'kg','section':'base'},
            {'productId':cocoa['id'],'amount':'0.030','unit':'kg','section':'variegato'},
        ],referenceIngredients=[
            {'name':'Water','amount':'0.1','unit':'kg','section':'base'},
            {'name':'Water','amount':'0.01','unit':'kg','section':'variegato'},
        ]))
    assert len(made['ingredients'])==2
    assert {item.get('section','base') for item in made['ingredients']}=={'base','variegato'}
    assert {item.get('section','base') for item in made['referenceIngredients']}=={'base','variegato'}
    preview=service.preview(i.tokens['owner'],{'businessDate':'2026-10-21','entries':[
        {'recipeId':made['id'],'revisionId':made['revisionId'],'batches':2}]})
    assert preview['deductions']==[{
        'productId':cocoa['id'],'name':'Cocoa Crumbolé','baseUnit':'kg',
        'recipeAmount':'0.66','allowanceAmount':'0.0066','quantity':'0.6666',
        'balance':'20','remaining':'19.3334'}]
    confirmed=service.confirm(i.tokens['owner'],fields(
        i,logId=str(uuid4()),confirmed=True,businessDate='2026-10-21',
        entries=[{'recipeId':made['id'],'revisionId':made['revisionId'],'batches':2}]))
    assert len(confirmed['ingredients'])==1 and confirmed['ingredients'][0]['quantity']=='0.6666'
    with i.connect() as db:
        assert db.execute("SELECT count(*) FROM inventory_stock_movements WHERE kind='production'").fetchone()==(1,)


def test_section_duplicates_values_and_legacy_flattening_are_strict(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); cocoa=stock(i)
    base={'productId':cocoa['id'],'amount':'0.3','unit':'kg'}
    denied('invalid',lambda:service.create_recipe(i.tokens['owner'],fields(
        i,name='Duplicate',yieldAmount='1',yieldUnit='tray',ingredients=[base,base],referenceIngredients=[])))
    denied('invalid',lambda:service.create_recipe(i.tokens['owner'],fields(
        i,name='Bad section',yieldAmount='1',yieldUnit='tray',
        ingredients=[{**base,'section':'topping'}],referenceIngredients=[])))
    denied('invalid',lambda:service.create_recipe(i.tokens['owner'],fields(
        i,name='Reference duplicate',yieldAmount='1',yieldUnit='tray',ingredients=[],referenceIngredients=[
            {'name':'Water','amount':'1','unit':'kg','section':'variegato'},
            {'name':' water ','amount':'2','unit':'kg','section':'variegato'}])))
    made=service.create_recipe(i.tokens['owner'],fields(
        i,name='Sectioned',yieldAmount='1',yieldUnit='tray',ingredients=[
            {**base,'section':'base'},{**base,'amount':'0.03','section':'variegato'}],referenceIngredients=[]))
    denied('invalid',lambda:service.edit_recipe(i.tokens['owner'],made['id'],fields(
        i,version=made['version'],name='Flattened',yieldAmount='1',yieldUnit='tray',
        ingredients=[base],referenceIngredients=[])))


def test_variegato_edit_requires_section_metadata_on_every_submitted_line(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts)
    made=service.create_recipe(i.tokens['owner'],fields(
        i,name='Reference topping',yieldAmount='1',yieldUnit='tray',ingredients=[],referenceIngredients=[
            {'name':'Water','amount':'1','unit':'kg','section':'base'},
            {'name':'Raspberries','amount':'0.1','unit':'kg','section':'variegato'}]))
    denied('invalid',lambda:service.edit_recipe(i.tokens['owner'],made['id'],fields(
        i,version=made['version'],name='Partial metadata',yieldAmount='1',yieldUnit='tray',ingredients=[],
        referenceIngredients=[
            {'name':'Water','amount':'1','unit':'kg','section':'base'},
            {'name':'Raspberries','amount':'0.1','unit':'kg'}])))
    removed=service.edit_recipe(i.tokens['owner'],made['id'],fields(
        i,version=made['version'],name='Topping removed',yieldAmount='1',yieldUnit='tray',ingredients=[],
        referenceIngredients=[{'name':'Water','amount':'1','unit':'kg','section':'base'}]))
    assert removed['referenceIngredients']==[{'name':'Water','amount':'1','unit':'kg'}]


def test_legacy_recipe_and_lampone_reference_shapes_remain_base_by_default(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); cocoa=stock(i)
    made=service.create_recipe(i.tokens['owner'],fields(
        i,name='Lampone',yieldAmount='1',yieldUnit='tray',instructions='',
        ingredients=[{'productId':cocoa['id'],'amount':'0.2','unit':'kg'}],
        referenceIngredients=[{'name':'Raspberries','amount':'0.1','unit':'kg'}]))
    assert 'section' not in made['ingredients'][0]
    assert made['referenceIngredients']==[{'name':'Raspberries','amount':'0.1','unit':'kg'}]
    edited=service.edit_recipe(i.tokens['owner'],made['id'],fields(
        i,version=made['version'],name='Fragola',yieldAmount='1',yieldUnit='tray',instructions='',
        ingredients=[{'productId':cocoa['id'],'amount':'0.25','unit':'kg'}],
        referenceIngredients=[{'name':'Strawberries','amount':'0.1','unit':'kg'}]))
    assert edited['referenceIngredients']==[{'name':'Strawberries','amount':'0.1','unit':'kg'}]


def test_explicit_and_implicit_base_sections_share_idempotency_fingerprint(inventory):
    i=inventory; service=ProductionService(i.connect,i.accounts); cocoa=stock(i)
    request=fields(i,name='Legacy retry',yieldAmount='1',yieldUnit='tray',instructions='',
                   ingredients=[{'productId':cocoa['id'],'amount':'0.2','unit':'kg'}],
                   referenceIngredients=[{'name':'Water','amount':'0.1','unit':'kg'}])
    created=service.create_recipe(i.tokens['owner'],request)
    retried=service.create_recipe(i.tokens['owner'],{
        **request,
        'ingredients':[{**request['ingredients'][0],'section':'base'}],
        'referenceIngredients':[{**request['referenceIngredients'][0],'section':'base'}],
    })
    assert retried==created
    old_shape={'name':'Legacy retry','yieldAmount':Decimal('1'),'yieldUnit':'tray','instructions':'',
               'ingredients':[{'productId':cocoa['id'],'amount':Decimal('0.2'),'unit':'kg'}],
               'referenceIngredients':[{'name':'Water','amount':Decimal('0.1'),'unit':'kg'}]}
    with i.connect() as db:
        stored=db.execute('SELECT fingerprint FROM production_requests WHERE request_id=%s',
                          (request['requestId'],)).fetchone()[0]
    assert stored==valid.fingerprint('recipe.created',old_shape)


def test_upgrade_027_preserves_populated_026_recipe_and_is_repeatable(empty_database,tmp_path):
    before_027=tmp_path/'before-027'; before_027.mkdir()
    for path in MIGRATIONS.glob('*.sql'):
        if path.name<'027_': (before_027/path.name).symlink_to(path.resolve())
    connect=lambda:psycopg.connect(empty_database)
    migrate(connect,directory=before_027)
    product_id,recipe_id,revision_id=(str(uuid4()) for _ in range(3))
    with connect() as db:
        business=db.execute("INSERT INTO businesses(name) VALUES('027 upgrade') RETURNING id").fetchone()[0]
        user=db.execute("""INSERT INTO account_users(username,display_name,password_salt,password_hash)
            VALUES('upgrade-027','Owner','salt','hash') RETURNING id""").fetchone()[0]
        db.execute("INSERT INTO inventory_products(id,business_id,sku,name,base_unit) VALUES(%s,%s,'OLD-027','Old cocoa','kg')",(product_id,business))
        db.execute("INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,'OLD-027')",(business,product_id))
        db.execute("INSERT INTO production_recipes(id,business_id,current_revision_id,created_by) VALUES(%s,%s,NULL,%s)",(recipe_id,business,user))
        db.execute("""INSERT INTO production_recipe_revisions
            (id,business_id,recipe_id,revision_number,name,yield_amount,yield_unit,instructions,reference_ingredients,created_by)
            VALUES(%s,%s,%s,1,'Existing tiramisu',1,'tray','Keep me','[{"name":"Water","amount":"1","unit":"kg"}]',%s)""",
                   (revision_id,business,recipe_id,user))
        db.execute("""INSERT INTO production_recipe_ingredients
            (business_id,recipe_id,revision_id,product_id,name,sku,amount,unit,base_unit,base_amount)
            VALUES(%s,%s,%s,%s,'Old cocoa','OLD-027',0.3,'kg','kg',0.3)""",
                   (business,recipe_id,revision_id,product_id))
        db.execute("UPDATE production_recipe_revisions SET sealed=true WHERE id=%s",(revision_id,))
        db.execute("UPDATE production_recipes SET current_revision_id=%s WHERE id=%s",(revision_id,recipe_id))
        revision=db.execute('SELECT * FROM production_recipe_revisions WHERE id=%s',(revision_id,)).fetchone()
        ingredient=db.execute('SELECT * FROM production_recipe_ingredients WHERE revision_id=%s',(revision_id,)).fetchone()
    assert migrate(connect)==['027_recipe_ingredient_sections.sql']
    with connect() as db:
        assert db.execute('SELECT * FROM production_recipe_revisions WHERE id=%s',(revision_id,)).fetchone()==revision
        upgraded=db.execute('SELECT * FROM production_recipe_ingredients WHERE revision_id=%s',(revision_id,)).fetchone()
        assert upgraded[:-1]==ingredient and upgraded[-1]=='base'
    with pytest.raises(psycopg.errors.CheckViolation),connect() as db:
        db.execute("UPDATE production_recipe_ingredients SET section='variegato' WHERE revision_id=%s",(revision_id,))
    assert migrate(connect)==[]
