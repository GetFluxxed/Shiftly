"""Forecast recovery and authorization checks independent of provider output."""
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID,uuid4

import pytest

from backend.shiftly.forecasts import ForecastService
from backend.shiftly.forecasts.repository import ForecastRepository
from backend.shiftly.identity.contracts import IdentityError


def service(i):
    return ForecastService(i.connect,i.accounts,model='test-model')


def request(i):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0]}


def test_expired_forecast_claim_is_recovered_and_old_worker_cannot_write(inventory):
    api=service(inventory);repo=ForecastRepository()
    api.generate(inventory.tokens['owner'],request(inventory))
    with inventory.connect() as db:first=repo.claim(db)
    with inventory.connect() as db:
        db.execute("UPDATE store_forecast_jobs SET lease_expires_at=NOW()-INTERVAL '1 second' WHERE forecast_id=%s",(first[0],))
        assert repo.complete(db,first[0],first[1],None) is False
        assert repo.fail(db,first[0],first[1],1,'Late failure') is False
    with inventory.connect() as db:second=repo.claim(db)
    assert second[0]==first[0] and second[1]!=first[1] and second[2]==2
    with inventory.connect() as db:
        assert repo.complete(db,first[0],first[1],None) is False
        assert repo.fail(db,first[0],first[1],1,'Old worker') is False
        assert repo.complete(db,second[0],second[1],None) is True
    assert api.get(inventory.tokens['owner'])['status']=='ready'


def test_expired_final_attempt_becomes_terminal_and_request_replay_does_not_requeue(inventory):
    api=service(inventory);repo=ForecastRepository();original=request(inventory)
    queued=api.generate(inventory.tokens['owner'],original)
    with inventory.connect() as db:claim=repo.claim(db)
    with inventory.connect() as db:
        db.execute("""UPDATE store_forecast_jobs SET attempts=5,lease_expires_at=NOW()-INTERVAL '1 second'
            WHERE forecast_id=%s""",(claim[0],))
    with inventory.connect() as db:
        assert repo.claim(db) is None
        assert repo.complete(db,claim[0],claim[1],None) is False
        assert db.execute('SELECT state,terminal FROM store_forecast_jobs WHERE forecast_id=%s',(claim[0],)).fetchone()==('failed',True)
    assert api.generate(inventory.tokens['owner'],original)['status']=='failed'
    fresh=request(inventory);retried=api.generate(inventory.tokens['owner'],fresh)
    assert retried['status']=='queued' and retried['forecast']['id']==queued['forecast']['id']
    with inventory.connect() as db:retry_claim=repo.claim(db)
    assert api.generate(inventory.tokens['owner'],fresh)['status']=='processing'
    with inventory.connect() as db:
        assert db.execute('SELECT attempts,lease_token FROM store_forecast_jobs WHERE forecast_id=%s',(claim[0],)).fetchone()==(1,UUID(retry_claim[1]))


def test_concurrent_same_request_creates_one_forecast_and_job(inventory):
    api=service(inventory);fields=request(inventory)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(lambda _:api.generate(inventory.tokens['owner'],fields),range(2)))
    assert results[0]['forecast']['id']==results[1]['forecast']['id']
    with inventory.connect() as db:
        assert db.execute('SELECT count(*) FROM store_forecasts').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM store_forecast_jobs').fetchone()==(1,)
        assert db.execute('SELECT count(*) FROM store_forecast_requests').fetchone()==(1,)


def test_forecast_permission_alone_cannot_expose_underlying_private_sources(inventory):
    with inventory.connect() as db:
        for table in ('business_memberships','account_store_memberships'):
            db.execute(f"UPDATE {table} SET capabilities=ARRAY['forecasts.view']::text[] WHERE user_id=%s",(inventory.users['delegate'],))
    api=service(inventory)
    with pytest.raises(IdentityError) as denied:api.get(inventory.tokens['delegate'])
    assert denied.value.code=='forbidden'
    with pytest.raises(IdentityError):api.generate(inventory.tokens['delegate'],request(inventory))
    with pytest.raises(IdentityError):api.generate(inventory.tokens['manager'],{
        **request(inventory),'expectedStoreId':inventory.stores[1]})
    with inventory.connect() as db:assert db.execute('SELECT count(*) FROM store_forecasts').fetchone()==(0,)


def test_sufficient_history_runs_validated_advisory_without_stock_writes(inventory):
    from datetime import date,timedelta
    import json
    from backend.shiftly.forecasts import ForecastWorker
    from backend.shiftly.production.service import ProductionService
    from tests.inventory_services.test_production import stock,recipe,submission
    production=ProductionService(inventory.connect,inventory.accounts)
    product=stock(inventory,amount='100');made=recipe(inventory,production,product)
    for offset in range(7):
        production.confirm(inventory.tokens['owner'],{
            **submission(inventory,made),'businessDate':(date.today()-timedelta(days=offset)).isoformat()})
    api=service(inventory);api.generate(inventory.tokens['owner'],request(inventory));seen=[]
    with inventory.connect() as db:
        before=db.execute('SELECT quantity,version FROM inventory_stock_balances WHERE store_id=%s AND product_id=%s',
                          (inventory.stores[0],product['id'])).fetchone()
    def provider(report,prompt):
        source=json.loads(report['notes']);seen.append(source)
        candidate=source['recipes'][0]
        return {'summary':'Review this suggestion against actual demand.','trends':['Seven recorded production days.'],
            'recommendations':[{'recipeId':candidate['id'],'name':candidate['name'],
                'day':(date.fromisoformat(source['snapshotDate'])+timedelta(days=1)).isoformat(),
                'batches':2,'rationale':'Recent recorded batches; demand is unknown.'}],
            'risks':['No sales history.'],'limitations':['Production does not establish demand.']}
    assert ForecastWorker(inventory.connect,provider).run_one() is True
    result=api.get(inventory.tokens['owner'])
    assert len(seen)==1 and result['status']=='ready'
    assert result['forecast']['analysis']['recommendations'][0]['recipeId']==made['id']
    assert result['forecast']['stale'] is False
    with inventory.connect() as db:
        after=db.execute('SELECT quantity,version FROM inventory_stock_balances WHERE store_id=%s AND product_id=%s',
                         (inventory.stores[0],product['id'])).fetchone()
    assert after==before
