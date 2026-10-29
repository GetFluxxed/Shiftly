from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production.service import ProductionService


def fields(i,**values):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**values}


def denied(code,operation):
    with pytest.raises(IdentityError) as caught:operation()
    assert caught.value.code==code
    return caught.value


def stock(i,amount='20'):
    product=i.service.create_product(i.tokens['owner'],fields(i,name='Cocoa powder',sku='COCOA-1',baseUnit='kg'))
    shelf=i.service.create_shelf(i.tokens['owner'],fields(i,name='Production shelf'))
    i.service.place(i.tokens['owner'],shelf['id'],product['id'],fields(i,version=shelf['version'],active=True))
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-28'))
    line=i.counts.lines(i.tokens['owner'],count['id'])['items'][0]
    saved=i.counts.save(i.tokens['owner'],count['id'],line['id'],fields(i,version=1,entry={'mode':'total','amount':amount,'unit':'kg'}))
    reviewed=i.counts.transition(i.tokens['owner'],count['id'],'review',fields(i,version=saved['count']['version']))
    i.counts.transition(i.tokens['owner'],count['id'],'post',fields(i,version=reviewed['version']))
    return product


def recipe(i,service,product,amount='2'):
    return service.create_recipe(i.tokens['owner'],fields(i,name='Chocolate base',yieldAmount='10',yieldUnit='each',instructions='Mix.',
        ingredients=[{'productId':product['id'],'amount':amount,'unit':'kg'}]))


def submission(i,recipe,**values):
    return fields(i,logId=str(uuid4()),confirmed=True,businessDate='2026-09-29',
                  entries=[{'recipeId':recipe['id'],'revisionId':recipe['revisionId'],'batches':2}],**values)


def test_revisioned_recipes_and_exact_one_percent_consumption(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i);first=recipe(i,service,product)
    edited=service.edit_recipe(i.tokens['owner'],first['id'],fields(i,version=first['version'],name='Dark chocolate base',yieldAmount='10',yieldUnit='each',instructions='',
        ingredients=[{'productId':product['id'],'amount':'1.5','unit':'kg'}]))
    assert edited['version']==2 and edited['revisionId']!=first['revisionId']
    assert service.recipe(i.tokens['owner'],first['id'])['name']=='Dark chocolate base'
    denied('conflict',lambda:service.preview(i.tokens['owner'],{'businessDate':'2026-09-29','entries':[{'recipeId':first['id'],'revisionId':first['revisionId'],'batches':2}]}))
    preview=service.preview(i.tokens['owner'],{'businessDate':'2026-09-29','entries':[{'recipeId':edited['id'],'revisionId':edited['revisionId'],'batches':2}]})
    assert preview['canConfirm'] is True
    assert preview['entries']==[{'recipeId':edited['id'],'revisionId':edited['revisionId'],'name':'Dark chocolate base',
                                 'yieldAmount':'10','yieldUnit':'each','batches':2}]
    assert preview['deductions'][0]|{'x':1}=={'productId':product['id'],'name':'Cocoa powder','baseUnit':'kg','recipeAmount':'3','allowanceAmount':'0.03','quantity':'3.03','balance':'20','remaining':'16.97','x':1}
    body=submission(i,edited);confirmed=service.confirm(i.tokens['owner'],body)
    assert confirmed['state']=='confirmed' and confirmed['ingredients'][0]['quantity']=='3.03'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='16.97'
    assert service.confirm(i.tokens['owner'],body)==confirmed
    replay={**body,'requestId':str(uuid4())}
    assert service.confirm(i.tokens['manager'],replay)==confirmed


def test_confirmation_is_atomic_for_unknown_or_insufficient_stock(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i,amount='1');made=recipe(i,service,product)
    entries=submission(i,made)['entries']
    preview=service.preview(i.tokens['owner'],{'businessDate':'2026-09-29','entries':entries})
    assert preview['canConfirm'] is False and preview['issues'][0]['code']=='insufficient_stock'
    denied('conflict',lambda:service.confirm(i.tokens['owner'],submission(i,made)))
    assert service.logs(i.tokens['owner'])['items']==[]
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='1'


def test_full_reversal_and_count_supersession_guard(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i);made=recipe(i,service,product);log=service.confirm(i.tokens['owner'],submission(i,made))
    reversed_log=service.reverse(i.tokens['owner'],log['id'],fields(i,reason='Entry was duplicated'))
    assert reversed_log['state']=='reversed' and reversed_log['reversalReason']=='Entry was duplicated'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='20'
    second=service.confirm(i.tokens['owner'],submission(i,made))
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-29'))
    line=i.counts.lines(i.tokens['owner'],count['id'])['items'][0]
    saved=i.counts.save(i.tokens['owner'],count['id'],line['id'],fields(i,version=1,entry={'mode':'total','amount':'15','unit':'kg'}))
    reviewed=i.counts.transition(i.tokens['owner'],count['id'],'review',fields(i,version=saved['count']['version']))
    i.counts.transition(i.tokens['owner'],count['id'],'post',fields(i,version=reviewed['version']))
    denied('conflict',lambda:service.reverse(i.tokens['owner'],second['id'],fields(i,reason='Too late')))


def test_precision_stale_version_and_log_id_conflicts(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i);made=recipe(i,service,product,amount='0.000000001')
    denied('invalid',lambda:service.preview(i.tokens['owner'],{'businessDate':'2026-09-29','entries':[{'recipeId':made['id'],'revisionId':made['revisionId'],'batches':1}]}))
    denied('conflict',lambda:service.edit_recipe(i.tokens['owner'],made['id'],fields(i,version=99,name='Changed',yieldAmount='1',yieldUnit='each',instructions='',ingredients=[{'productId':product['id'],'amount':'1','unit':'kg'}])))
    body=submission(i,recipe(i,service,product));service.confirm(i.tokens['owner'],body)
    changed={**body,'requestId':str(uuid4()),'entries':[{**body['entries'][0],'batches':3}]}
    denied('conflict',lambda:service.confirm(i.tokens['owner'],changed))


def test_recipe_order_yield_labels_and_native_cookie_api_parity(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i)
    recipes=[]
    for name in ('Zulu','alpha','Éclair'):
        recipes.append(service.create_recipe(i.tokens['owner'],fields(i,name=name,yieldAmount='1',yieldUnit='batch',instructions='',
            ingredients=[{'productId':product['id'],'amount':'0.1','unit':'kg'}])))
    listed=service.recipes(i.tokens['owner'])
    assert [item['name'] for item in listed['items']]==['alpha','Zulu','Éclair']
    selected=recipes[0]
    entries=[{'recipeId':selected['id'],'revisionId':selected['revisionId'],'batches':1}]
    native_headers={'Authorization':'Bearer '+i.tokens['owner']}
    native=i.client.get('/api/mobile/production/recipes',headers=native_headers)
    assert native.status_code==200,native.text
    native_preview=i.client.post('/api/mobile/production/preview',headers=native_headers,json={'businessDate':'2026-09-29','entries':entries})
    assert native_preview.status_code==200,native_preview.text
    i.client.cookies.set('shiftly_account_session',i.tokens['owner'])
    browser=i.client.get('/api/production/recipes')
    browser_preview=i.client.post('/api/production/preview',json={'businessDate':'2026-09-29','entries':entries})
    assert browser.status_code==200 and browser.json()==native.json()
    assert browser_preview.status_code==200 and browser_preview.json()==native_preview.json()


def test_archived_ingredient_blocks_new_production_and_completed_evidence_is_sealed(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i);made=recipe(i,service,product)
    log=service.confirm(i.tokens['owner'],submission(i,made))
    with pytest.raises(psycopg.errors.CheckViolation),i.connect() as db:
        db.execute('''INSERT INTO production_log_entries(business_id,store_id,log_id,sequence,recipe_id,revision_id,name,yield_amount,yield_unit,batches)
          SELECT business_id,store_id,log_id,99,recipe_id,revision_id,name,yield_amount,yield_unit,batches
          FROM production_log_entries WHERE log_id=%s LIMIT 1''',(log['id'],))
    with pytest.raises(psycopg.errors.CheckViolation),i.connect() as db:
        db.execute('''INSERT INTO production_recipe_ingredients(business_id,recipe_id,revision_id,product_id,name,sku,amount,unit,base_unit,base_amount)
          SELECT business_id,recipe_id,revision_id,product_id,name,sku,amount,unit,base_unit,base_amount
          FROM production_recipe_ingredients WHERE revision_id=%s LIMIT 1''',(made['revisionId'],))
    service_product=i.service.product(i.tokens['owner'],product['id'])
    i.service.product_state(i.tokens['owner'],product['id'],fields(i,version=service_product['version'],active=False))
    preview=service.preview(i.tokens['owner'],{'businessDate':'2026-09-29','entries':[{'recipeId':made['id'],'revisionId':made['revisionId'],'batches':1}]})
    assert preview['canConfirm'] is False and preview['issues'][0]['code']=='unknown_stock'


def test_concurrent_confirmations_serialize_stock_and_same_log_is_exactly_once(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i);made=recipe(i,service,product)
    first,second=submission(i,made),submission(i,made)
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda body:service.confirm(i.tokens['owner'],body),(first,second)))
    assert {result['id'] for result in results}=={first['logId'],second['logId']}
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='11.92'
    shared=submission(i,made)
    owner_body={**shared,'requestId':str(uuid4())}
    manager_body={**shared,'requestId':str(uuid4())}
    with ThreadPoolExecutor(2) as pool:
        same=list(pool.map(lambda pair:service.confirm(pair[0],pair[1]),
                           ((i.tokens['owner'],owner_body),(i.tokens['manager'],manager_body))))
    assert same[0]==same[1] and same[0]['id']==shared['logId']
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='7.88'
    with i.connect() as db:
        assert db.execute("SELECT count(*) FROM inventory_stock_movements WHERE kind='production'").fetchone()==(3,)
        assert db.execute('SELECT count(*) FROM production_logs').fetchone()==(3,)


def test_failure_after_first_movement_rolls_back_every_production_write(inventory,monkeypatch):
    i=inventory;service=ProductionService(i.connect,i.accounts)
    products=[i.service.create_product(i.tokens['owner'],fields(i,name=name,sku=sku,baseUnit='kg'))
              for name,sku in (('Cocoa','ROLL-1'),('Sugar','ROLL-2'))]
    shelf=i.service.create_shelf(i.tokens['owner'],fields(i,name='Rollback shelf'))
    for product in products:
        current=i.service.shelf(i.tokens['owner'],shelf['id'])
        i.service.place(i.tokens['owner'],shelf['id'],product['id'],fields(i,version=current['version'],active=True))
    count=i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-28'))
    saved=None
    for line in i.counts.lines(i.tokens['owner'],count['id'])['items']:
        saved=i.counts.save(i.tokens['owner'],count['id'],line['id'],fields(i,version=1,entry={'mode':'total','amount':'20','unit':'kg'}))
    reviewed=i.counts.transition(i.tokens['owner'],count['id'],'review',fields(i,version=saved['count']['version']))
    i.counts.transition(i.tokens['owner'],count['id'],'post',fields(i,version=reviewed['version']))
    made=service.create_recipe(i.tokens['owner'],fields(i,name='Two ingredient base',yieldAmount='1',yieldUnit='batch',instructions='',
        ingredients=[{'productId':p['id'],'amount':'1','unit':'kg'} for p in products]))
    original=service.movements.apply;calls=0
    def fail_second(*args,**kwargs):
        nonlocal calls
        calls+=1
        if calls==2:raise RuntimeError('injected after first movement')
        return original(*args,**kwargs)
    monkeypatch.setattr(service.movements,'apply',fail_second)
    with pytest.raises(RuntimeError):service.confirm(i.tokens['owner'],submission(i,made))
    assert [item['quantity'] for item in i.counts.stock(i.tokens['owner'])['items']]==['20','20']
    with i.connect() as db:
        assert db.execute("SELECT count(*) FROM inventory_stock_movements WHERE kind='production'").fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM production_logs').fetchone()==(0,)
        assert db.execute('SELECT count(*) FROM production_requests').fetchone()==(1,)


def test_production_role_scope_report_denial_and_view_required_for_writes(inventory):
    i=inventory;service=ProductionService(i.connect,i.accounts);product=stock(i);made=recipe(i,service,product)
    with i.connect() as db:
        db.execute("UPDATE account_store_memberships SET role='production',capabilities='{}' WHERE user_id=%s",(i.users['noinventory'],))
        db.execute("UPDATE account_store_memberships SET role='admin',capabilities=ARRAY['production.submit'] WHERE user_id=%s",(i.users['delegate'],))
    production=i.tokens['noinventory']
    assert service.recipe(production,made['id'])['id']==made['id']
    denied('forbidden',lambda:service.create_recipe(production,fields(i,name='Forbidden',yieldAmount='1',yieldUnit='batch',instructions='',ingredients=[{'productId':product['id'],'amount':'1','unit':'kg'}])))
    denied('forbidden',lambda:service.confirm(i.tokens['delegate'],submission(i,made)))
    report=i.client.post('/api/mobile/reports',headers={'Authorization':'Bearer '+production},json={'expectedStoreId':i.stores[0]})
    assert report.status_code==403
    confirmed=service.confirm(production,submission(i,made))
    assert service.logs(i.second)['items']==[]
    denied('not_found',lambda:service.log(i.second,confirmed['id']))
    denied('conflict',lambda:service.confirm(i.second,submission(i,made,expectedStoreId=i.stores[0])))
