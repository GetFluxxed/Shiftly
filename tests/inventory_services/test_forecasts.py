from uuid import uuid4
from types import SimpleNamespace
import json

import pytest

from backend.shiftly.forecasts import ForecastService,ForecastWorker
from backend.shiftly.forecasts.service import PROMPT_VERSION
from backend.shiftly.forecasts.repository import ForecastRepository
from backend.shiftly.forecasts.validation import analysis
from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.production.service import ProductionService
from tests.inventory_services.test_production import stock,recipe,submission


def fields(i,**values):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**values}


def service(i,*,available=True):
    return ForecastService(i.connect,i.accounts,model='test-model',provider_available=available)


def test_manual_generate_is_store_scoped_idempotent_and_sparse_without_fake_analysis(inventory):
    forecasts=service(inventory)
    request=fields(inventory)
    queued=forecasts.generate(inventory.tokens['owner'],request)
    assert queued['status']=='queued' and queued['forecast']['coverage']['productionDays']==0
    with inventory.connect() as db:
        db.execute("""INSERT INTO reports(id,store_id,employee,shift,notes,report_hash)
            VALUES(%s,%s,'Crew','closing','New evidence',repeat('e',64))""",
            (str(uuid4()),inventory.stores[0]))
    replay=forecasts.generate(inventory.tokens['owner'],request)
    assert replay['forecast']['id']==queued['forecast']['id'] and replay['forecast']['stale'] is True
    called=[]
    worker=ForecastWorker(inventory.connect,lambda *_:called.append(True))
    assert worker.run_one() is True and called==[]
    ready=forecasts.get(inventory.tokens['owner'])
    assert ready['status']=='ready' and ready['forecast']['analysis'] is None
    assert ready['forecast']['facts']=={'daily':[],'ingredients':[]}
    assert forecasts.get(inventory.tokens['foreign'])['status']=='not_requested'
    with pytest.raises(IdentityError) as denied:
        forecasts.get(inventory.tokens['delegate'])
    assert denied.value.code=='forbidden'


def test_provider_absent_keeps_exact_facts_and_never_claims_to_be_ready(inventory):
    forecasts=service(inventory,available=False)
    result=forecasts.generate(inventory.tokens['owner'],fields(inventory))
    assert result['status']=='unavailable'
    assert result['forecast']['facts']=={'daily':[],'ingredients':[]}
    assert result['forecast']['analysis'] is None
    assert 'not configured' in result['error']


def test_request_reuse_and_revoked_capability_fail_before_replay(inventory):
    forecasts=service(inventory); request=fields(inventory)
    forecasts.generate(inventory.tokens['manager'],request)
    changed={**request,'logId':str(uuid4())}
    with pytest.raises(IdentityError):forecasts.generate(inventory.tokens['manager'],changed)
    with inventory.connect() as db:
        db.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s AND store_id=%s",
                   (inventory.users['manager'],inventory.stores[0]))
    with pytest.raises(IdentityError) as denied:forecasts.generate(inventory.tokens['manager'],request)
    assert denied.value.code=='forbidden'


def test_invalid_provider_output_fails_closed_and_queue_claim_is_fenced(inventory):
    forecasts=service(inventory); queued=forecasts.generate(inventory.tokens['owner'],fields(inventory))
    with inventory.connect() as db:
        db.execute("""UPDATE store_forecasts SET source_snapshot=jsonb_set(source_snapshot,
            '{coverage,productionDays}','7'::jsonb) WHERE id=%s""",(queued['forecast']['id'],))
    worker=ForecastWorker(inventory.connect,lambda *_:{'summary':'invented'})
    assert worker.run_one() is False
    failed=forecasts.get(inventory.tokens['owner'])
    assert failed['status']=='failed' and failed['forecast']['analysis'] is None
    assert failed['error']=='Forecast generation failed.'
    with inventory.connect() as db:
        db.execute("""UPDATE store_forecast_jobs SET state='failed',attempts=5,terminal=true,
            lease_token=NULL,lease_expires_at=NULL WHERE forecast_id=%s""",(queued['forecast']['id'],))
    retried=forecasts.generate(inventory.tokens['owner'],fields(inventory))
    assert retried['forecast']['id']==queued['forecast']['id'] and retried['status']=='queued'
    repository=ForecastRepository()
    with inventory.connect() as db:
        retried_claim=repository.claim(db)
        assert repository.complete(db,retried_claim[0],retried_claim[1],None)

    with inventory.connect() as db:
        db.execute("""INSERT INTO reports(id,store_id,employee,shift,notes,report_hash)
            VALUES(%s,%s,'Crew','opening','Changed source',repeat('f',64))""",
            (str(uuid4()),inventory.stores[0]))
    other=service(inventory); other.generate(inventory.tokens['owner'],fields(inventory))
    with inventory.connect() as first:
        claim=repository.claim(first)
    with inventory.connect() as second:
        assert repository.claim(second) is None
        assert repository.complete(second,claim[0],str(uuid4()),None) is False


def test_confirmation_enqueues_exact_facts_and_recipe_or_reversal_makes_snapshot_stale(inventory):
    forecasts=service(inventory)
    production=ProductionService(inventory.connect,inventory.accounts,
                                 forecast_enqueue=forecasts.enqueue_after_confirmation)
    ingredient=stock(inventory,amount='20'); made=recipe(inventory,production,ingredient)
    log=production.confirm(inventory.tokens['owner'],submission(inventory,made))
    queued=forecasts.get(inventory.tokens['owner'])
    assert queued['status']=='queued'
    assert queued['forecast']['coverage']['productionReports']==1
    assert queued['forecast']['facts']['daily'][0]['batches']==2
    used=queued['forecast']['facts']['ingredients'][0]
    assert used['usedAmount']=='4.04' and used['quantity']=='15.96'
    with inventory.connect() as db:
        source=db.execute('SELECT source_snapshot FROM store_forecasts WHERE id=%s',
                          (queued['forecast']['id'],)).fetchone()[0]
    assert source['recipes'][0]['yieldAmount']=='10'
    assert source['recipes'][0]['ingredients'][0]['baseAmount']=='2'
    assert source['productionEntries'][0]['revisionId']==made['revisionId']
    assert source['productionEntries'][0]['yieldAmount']=='10'
    assert source['productionDeductions'][0]['allowanceRule']=='1%'
    assert source['productionDeductions'][0]['recipeAmount']=='4'
    assert source['productionDeductions'][0]['allowanceAmount']=='0.04'
    assert source['stockAsOf'][0]['lastCountedAt'] is not None
    ForecastWorker(inventory.connect,lambda *_:pytest.fail('sparse history must not call provider')).run_one()
    assert forecasts.get(inventory.tokens['owner'])['forecast']['stale'] is False
    production.edit_recipe(inventory.tokens['owner'],made['id'],fields(
        inventory,version=made['version'],name='Revised base',yieldAmount='10',yieldUnit='each',instructions='',
        ingredients=[{'productId':ingredient['id'],'amount':'2','unit':'kg'}]))
    assert forecasts.get(inventory.tokens['owner'])['forecast']['stale'] is True
    production.reverse(inventory.tokens['owner'],log['id'],fields(inventory,reason='Correction'))
    regenerated=forecasts.generate(inventory.tokens['owner'],fields(inventory))
    assert regenerated['forecast']['coverage']['productionReports']==0
    with pytest.raises(IdentityError) as hidden:
        forecasts.generate(inventory.tokens['foreign'],{
            'requestId':str(uuid4()),'expectedStoreId':inventory.stores[2],'logId':log['id']})
    assert hidden.value.code=='not_found'


def test_native_route_returns_unavailable_without_provider_configuration(inventory):
    headers={'Authorization':'Bearer '+inventory.tokens['owner']}
    missing=inventory.client.get('/api/mobile/production/forecast',headers=headers)
    assert missing.status_code==200 and missing.json()['status']=='unavailable'
    created=inventory.client.post('/api/mobile/production/forecast',headers=headers,json=fields(inventory))
    assert created.status_code==200 and created.json()['status']=='unavailable'
    assert created.json()['forecast']['facts']=={'daily':[],'ingredients':[]}


def test_recipe_snapshot_keeps_all_ingredients_and_other_store_sentinels_are_isolated(inventory):
    forecasts=service(inventory); production=ProductionService(inventory.connect,inventory.accounts)
    listed=stock(inventory,amount='20')
    sentinel=inventory.service.create_product(inventory.tokens['owner'],fields(
        inventory,name='Second-store sentinel',sku='STORE-2-ONLY',baseUnit='kg'))
    partial=production.create_recipe(inventory.tokens['owner'],fields(
        inventory,name='Partially listed recipe',yieldAmount='1',yieldUnit='batch',instructions='',ingredients=[
            {'productId':listed['id'],'amount':'1','unit':'kg'},
            {'productId':sentinel['id'],'amount':'2','unit':'kg'}]))
    only_second=production.create_recipe(inventory.tokens['owner'],fields(
        inventory,name='Second-store recipe',yieldAmount='2',yieldUnit='batch',instructions='',ingredients=[
            {'productId':sentinel['id'],'amount':'1','unit':'kg'}]))
    with inventory.connect() as db:
        db.execute('''INSERT INTO inventory_store_products(business_id,store_id,product_id)
            VALUES(%s,%s,%s)''',(inventory.companies[0],inventory.stores[1],sentinel['id']))
        db.execute("""INSERT INTO reports(id,store_id,employee,shift,notes,report_hash)
            VALUES(%s,%s,'Crew','opening','SECOND STORE SENTINEL',repeat('d',64))""",
            (str(uuid4()),inventory.stores[1]))
    first=forecasts.generate(inventory.tokens['owner'],fields(inventory))
    second=forecasts.generate(inventory.second,{
        'requestId':str(uuid4()),'expectedStoreId':inventory.stores[1]})
    with inventory.connect() as db:
        first_source=db.execute('SELECT source_snapshot FROM store_forecasts WHERE id=%s',(first['forecast']['id'],)).fetchone()[0]
        second_source=db.execute('SELECT source_snapshot FROM store_forecasts WHERE id=%s',(second['forecast']['id'],)).fetchone()[0]
    saved=next(r for r in first_source['recipes'] if r['id']==partial['id'])
    assert saved['active'] is False and len(saved['ingredients'])==2
    assert all(r['id']!=only_second['id'] for r in first_source['recipes'])
    assert all('SECOND STORE SENTINEL' not in r['notes'] for r in first_source['shiftReports'])
    assert any(r['id']==only_second['id'] for r in second_source['recipes'])
    assert second_source['facts']['ingredients'][0]['productId']==sentinel['id']
    assert second_source['shiftReports'][0]['notes']=='SECOND STORE SENTINEL'


def test_model_validation_uses_snapshot_date_and_rejects_duplicates_or_oversize():
    source={'recipes':[{'id':'recipe-1','name':'Base','active':True}]}
    valid={'summary':'Advisory only.','trends':[],'recommendations':[
        {'recipeId':'recipe-1','name':'Base','day':'2026-10-02','batches':1,'rationale':'Recent production.'}],
        'risks':[],'limitations':['Production is not sales.']}
    assert analysis(valid,source,'2026-10-01')['recommendations'][0]['day']=='2026-10-02'
    with pytest.raises(ValueError):analysis({**valid,'recommendations':valid['recommendations']*2},source,'2026-10-01')
    with pytest.raises(ValueError):analysis({**valid,'summary':'x'*4001},source,'2026-10-01')
    with pytest.raises(ValueError):analysis({**valid,'recommendations':[
        {**valid['recommendations'][0],'day':'2026-10-05'}]},source,'2026-10-01')
    with pytest.raises(ValueError):analysis(valid,{'recipes':[{'id':'recipe-1','name':'Base','active':False}]},'2026-10-01')


def test_source_encoding_trims_every_large_array_coherently_below_hard_limit():
    facts={'daily':[{'date':'2026-10-01','recipeId':str(uuid4()),'name':'D'*160,'batches':1} for _ in range(300)],
           'ingredients':[{'productId':str(uuid4()),'name':'I'*160,'baseUnit':'kg','quantity':'1','usedAmount':'1'} for _ in range(600)]}
    coverage={'windowDays':28,'productionReports':300,'productionDays':28,'shiftReports':50,'truncated':True}
    source={'snapshotDate':'2026-10-01','facts':facts,'coverage':coverage,
            'recipes':[{'id':str(uuid4()),'name':'R'*160,'active':True} for _ in range(120)],
            'productionEntries':[{'logId':str(uuid4()),'name':'E'*160} for _ in range(300)],
            'productionDeductions':[{'logId':str(uuid4()),'name':'X'*160} for _ in range(600)],
            'stockAsOf':[{'productId':item['productId'],'lastCountedAt':None} for item in facts['ingredients']],
            'shiftReports':[{'id':str(uuid4()),'notes':'N'*4000} for _ in range(60)]}
    forecast=ForecastService(lambda:None,None,model='test-model')
    forecast.repository=SimpleNamespace(sources=lambda *_:(facts,coverage,source,None))
    returned_facts,_,bounded,_,_=forecast._snapshot(None,SimpleNamespace(business_id=1,store_id=1),None)
    raw=json.dumps([1,1,None,PROMPT_VERSION,'test-model',bounded],ensure_ascii=False,
                   sort_keys=True,separators=(',',':')).encode()
    assert len(raw)<=80000 and bounded['coverage']['truncated'] is True
    assert len(returned_facts['ingredients'])==len(bounded['stockAsOf'])
    assert bounded['included']['ingredients']==len(returned_facts['ingredients'])
    assert bounded['included']['productionDeductions']==len(bounded['productionDeductions'])


def test_selected_log_is_focus_context_while_history_keeps_seven_production_days(inventory):
    forecasts=service(inventory); production=ProductionService(inventory.connect,inventory.accounts)
    ingredient=stock(inventory,amount='50'); made=recipe(inventory,production,ingredient,amount='1')
    selected=None
    for day in ('2026-09-25','2026-09-26','2026-09-27','2026-09-28','2026-09-29','2026-09-30','2026-10-01'):
        selected=production.confirm(inventory.tokens['owner'],{**submission(inventory,made),'businessDate':day})
    result=forecasts.generate(inventory.tokens['owner'],fields(inventory,logId=selected['id']))
    assert result['forecast']['logId']==selected['id']
    assert result['forecast']['coverage']['productionDays']==7
    with inventory.connect() as db:
        source=db.execute('SELECT source_snapshot FROM store_forecasts WHERE id=%s',(result['forecast']['id'],)).fetchone()[0]
    assert source['focusProductionLogId']==selected['id']
    assert len({row['date'] for row in source['productionEntries']})==7
