from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import psycopg
import pytest

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.counts.validation import measurement


def fields(i, **values):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**values}


def setup_stock(i, *, shelves=1):
    product=i.service.create_product(i.tokens['owner'],fields(i,name='White Quella',sku='000184',baseUnit='kg',containerAmount='6'))
    placements=[]
    for index in range(shelves):
        shelf=i.service.create_shelf(i.tokens['owner'],fields(i,name=f'Shelf {index+1}'))
        i.service.place(i.tokens['owner'],shelf['id'],product['id'],fields(i,version=shelf['version'],active=True))
        placements.append(shelf)
    return product,placements


def start(i):
    return i.counts.start(i.tokens['owner'],fields(i,businessDate='2026-09-25'))


def observe_all(i, count, *, amount='13.25'):
    for line in i.counts.lines(i.tokens['owner'],count['id'])['items']:
        result=i.counts.save(i.tokens['owner'],count['id'],line['id'],fields(i,version=line['version'],entry={'mode':'total','amount':amount,'unit':'kg'}))
    return result['count']


def post(i, count):
    count=i.counts.transition(i.tokens['owner'],count['id'],'review',fields(i,version=count['version']))
    return i.counts.transition(i.tokens['owner'],count['id'],'post',fields(i,version=count['version']))


def denied(code, operation):
    with pytest.raises(IdentityError) as caught: operation()
    assert caught.value.code==code
    return caught.value


def test_full_count_draft_resume_review_post_and_history(inventory):
    i=inventory;p,_=setup_stock(i);c=start(i)
    line=i.counts.lines(i.tokens['owner'],c['id'])['items'][0]
    assert line['quantity'] is None and c['countedLines']==0
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None
    denied('conflict',lambda:i.counts.transition(i.tokens['owner'],c['id'],'review',fields(i,version=c['version'])))
    body=fields(i,version=1,entry={'mode':'containers','fullContainers':2,'partialAmount':'1250','partialUnit':'g'})
    saved=i.counts.save(i.tokens['owner'],c['id'],line['id'],body)
    assert saved['line']['quantity']=='13.25'
    assert i.counts.save(i.tokens['owner'],c['id'],line['id'],body)==saved
    assert i.counts.detail(i.tokens['owner'],c['id'])['countedLines']==1
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None
    comparison=i.counts.comparisons(i.tokens['owner'],c['id'])['items'][0]
    assert comparison['quantity']=='13.25' and comparison['previousQuantity'] is None and comparison['difference'] is None
    reviewed=i.counts.transition(i.tokens['owner'],c['id'],'review',fields(i,version=saved['count']['version']))
    denied('conflict',lambda:i.counts.save(i.tokens['owner'],c['id'],line['id'],fields(i,version=2,entry=body['entry'])))
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity'] is None
    final_body=fields(i,version=reviewed['version'])
    published=i.counts.transition(i.tokens['owner'],c['id'],'post',final_body)
    assert i.counts.transition(i.tokens['owner'],c['id'],'post',final_body)==published
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='13.25'
    detail=i.counts.stock_detail(i.tokens['owner'],p['id'])
    assert detail['locations']['items'][0]['entry']==body['entry']
    assert i.counts.history(i.tokens['owner'])['items'][0]['state']=='posted'
    with i.connect() as db:
        assert db.execute('SELECT count(*),sum(quantity_after) FROM inventory_stock_postings').fetchone()==(1,13.25)
    second=observe_all(i,start(i),amount='10')
    assert i.counts.comparisons(i.tokens['owner'],second['id'])['items'][0]['difference']=='-3.25'
    post(i,second)
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='10'
    assert i.counts.comparisons(i.tokens['owner'],c['id'])['items'][0]['quantity']=='13.25'


def test_location_totals_explicit_zero_and_unassigned(inventory):
    i=inventory;p,shelves=setup_stock(i,shelves=2);c=start(i)
    first=i.counts.lines(i.tokens['owner'],c['id'],shelf=shelves[0]['id'])['items'][0]
    i.counts.save(i.tokens['owner'],c['id'],first['id'],fields(i,version=1,entry={'mode':'total','amount':'0','unit':'kg'}))
    assert i.counts.comparisons(i.tokens['owner'],c['id'])['items'][0]['quantity'] is None
    remaining=i.counts.lines(i.tokens['owner'],c['id'],missing=True)['items']
    assert len(remaining)==1
    result=i.counts.save(i.tokens['owner'],c['id'],remaining[0]['id'],fields(i,version=1,entry={'mode':'total','amount':'1250','unit':'g'}))
    post(i,result['count'])
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='1.25'
    for shelf in shelves:
        live=i.service.shelf(i.tokens['owner'],shelf['id'])
        i.service.place(i.tokens['owner'],shelf['id'],p['id'],fields(i,version=live['version'],active=False))
    new=start(i)
    unassigned=i.counts.lines(i.tokens['owner'],new['id'],shelf='unassigned')['items']
    assert len(unassigned)==1 and unassigned[0]['shelfId'] is None


def test_changed_configuration_cancellation_and_historical_reference(inventory):
    i=inventory;p,_=setup_stock(i);old=post(i,observe_all(i,start(i)))
    current=start(i)
    i.service.edit_product(i.tokens['owner'],p['id'],fields(i,name='New name',sku='000185',containerAmount='7',version=p['version']))
    assert i.counts.detail(i.tokens['owner'],current['id'])['configurationChanged']
    counted=observe_all(i,current)
    denied('conflict',lambda:post(i,counted))
    cancelled=i.counts.transition(i.tokens['owner'],current['id'],'cancel',fields(i,version=counted['version']))
    assert cancelled['state']=='cancelled'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='13.25'
    previous=i.counts.comparisons(i.tokens['owner'],old['id'])['items'][0]
    assert previous['name']=='White Quella' and previous['containerAmount']=='6'
    assert start(i)['state']=='draft'


def test_scope_permissions_revocation_and_stale_versions(inventory):
    i=inventory;p,_=setup_stock(i);c=start(i);line=i.counts.lines(i.tokens['owner'],c['id'])['items'][0]
    denied('forbidden',lambda:i.counts.start(i.tokens['crew'],fields(i,businessDate='2026-09-25')))
    denied('forbidden',lambda:i.counts.dashboard(i.tokens['noinventory']))
    for token in (i.second,i.tokens['foreign']):
        denied('not_found',lambda:i.counts.detail(token,c['id']))
        denied('not_found',lambda:i.counts.stock_detail(token,p['id']))
        assert i.counts.stock(token)['items']==[]
    with i.connect() as db:
        db.execute("UPDATE account_store_memberships SET capabilities=ARRAY['inventory.view','counts.submit'] WHERE user_id=%s",(i.users['crew'],))
    body=fields(i,version=1,entry={'mode':'total','amount':'0','unit':'kg'})
    result=i.counts.save(i.tokens['crew'],c['id'],line['id'],body)
    denied('conflict',lambda:i.counts.save(i.tokens['owner'],c['id'],line['id'],fields(i,version=1,entry=body['entry'])))
    reviewed=i.counts.transition(i.tokens['crew'],c['id'],'review',fields(i,version=result['count']['version']))
    denied('forbidden',lambda:i.counts.transition(i.tokens['crew'],c['id'],'post',fields(i,version=reviewed['version'])))
    reopened=i.counts.transition(i.tokens['manager'],c['id'],'reopen',fields(i,version=reviewed['version']))
    assert reopened['state']=='draft'
    with i.connect() as db:
        db.execute("UPDATE account_store_memberships SET state='revoked' WHERE user_id=%s",(i.users['crew'],))
    denied('forbidden',lambda:i.counts.save(i.tokens['crew'],c['id'],line['id'],body))
    denied('conflict',lambda:i.counts.start(i.tokens['owner'],fields(i,expectedStoreId=i.stores[1],businessDate='2026-09-25')))


def test_concurrent_start_edit_and_post_are_safe(inventory):
    i=inventory;setup_stock(i)
    def attempt(operation):
        try:return operation()
        except IdentityError as error:return error.code
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(lambda _:attempt(lambda:start(i)),range(2)))
    assert results.count('conflict')==1
    c=next(item for item in results if isinstance(item,dict));line=i.counts.lines(i.tokens['owner'],c['id'])['items'][0]
    def save(amount):return attempt(lambda:i.counts.save(i.tokens['owner'],c['id'],line['id'],fields(i,version=1,entry={'mode':'total','amount':amount,'unit':'kg'})))
    with ThreadPoolExecutor(2) as pool: results=list(pool.map(save,['1','2']))
    assert results.count('conflict')==1
    saved=next(item for item in results if isinstance(item,dict))
    c=i.counts.transition(i.tokens['owner'],c['id'],'review',fields(i,version=saved['count']['version']))
    body=fields(i,version=c['version'])
    with ThreadPoolExecutor(2) as pool:
        results=list(pool.map(lambda _:i.counts.transition(i.tokens['owner'],c['id'],'post',body),range(2)))
    assert results[0]==results[1]
    with i.connect() as db:assert db.execute('SELECT count(*) FROM inventory_stock_postings').fetchone()[0]==1


def test_post_rollback_and_changed_baseline(inventory,monkeypatch):
    i=inventory;setup_stock(i);post(i,observe_all(i,start(i)))
    c=observe_all(i,start(i),amount='5')
    c=i.counts.transition(i.tokens['owner'],c['id'],'review',fields(i,version=c['version']))
    with monkeypatch.context() as patch:
        patch.setattr(i.counts.audit,'record',lambda *args:(_ for _ in ()).throw(RuntimeError('audit failed')))
        with pytest.raises(RuntimeError):i.counts.transition(i.tokens['owner'],c['id'],'post',fields(i,version=c['version']))
    assert i.counts.detail(i.tokens['owner'],c['id'])['state']=='review'
    assert i.counts.stock(i.tokens['owner'])['items'][0]['quantity']=='13.25'
    with i.connect() as db:db.execute('UPDATE inventory_stock_balances SET quantity=quantity+1')
    denied('conflict',lambda:i.counts.transition(i.tokens['owner'],c['id'],'post',fields(i,version=c['version'])))


@pytest.mark.parametrize('table', ['inventory_counts','inventory_count_products','inventory_count_lines','inventory_stock_postings'])
def test_posted_history_is_immutable_at_database_boundary(inventory,table):
    i=inventory;setup_stock(i);post(i,observe_all(i,start(i)))
    with pytest.raises(psycopg.errors.CheckViolation),i.connect() as db:
        db.execute('DELETE FROM '+table)
    column={'inventory_counts':'version','inventory_count_products':'product_version','inventory_count_lines':'version','inventory_stock_postings':'quantity_after'}[table]
    with pytest.raises(psycopg.errors.CheckViolation),i.connect() as db:db.execute(f'UPDATE {table} SET {column}={column}+1')


@pytest.mark.parametrize('entry', [None,{}, {'mode':'total','amount':'-1','unit':'kg'}, {'mode':'total','amount':'NaN','unit':'kg'},
    {'mode':'total','amount':'1','unit':'l'}, {'mode':'total','amount':1,'unit':'kg'},
    {'mode':'containers','fullContainers':True,'partialAmount':'0','partialUnit':'g'}])
def test_invalid_measurements(entry):
    denied('invalid',lambda:measurement(entry,{'base_unit':'kg','container_amount':6}))


def test_exact_mass_and_whole_item_rules():
    from decimal import Decimal
    assert measurement({'mode':'total','amount':'0.000001','unit':'g'},{'base_unit':'kg'})[0]==Decimal('0.000000001')
    assert measurement({'mode':'total','amount':'0','unit':'each'},{'base_unit':'each'})[0]==0
    denied('invalid',lambda:measurement({'mode':'total','amount':'0.5','unit':'each'},{'base_unit':'each'}))
    denied('invalid',lambda:measurement({'mode':'containers','fullContainers':1,'partialAmount':'0','partialUnit':'kg'},{'base_unit':'kg','container_amount':None}))


def test_native_count_endpoints(inventory):
    i=inventory;setup_stock(i);client=i.client;headers={'Authorization':'Bearer '+i.tokens['owner']}
    base='/api/mobile/inventory'
    assert client.get(base+'/stock',headers=headers).json()['items'][0]['quantity'] is None
    c=client.post(base+'/counts',headers=headers,json=fields(i,businessDate='2026-09-25'))
    assert c.status_code==200,c.text
    c=c.json();path=base+'/counts/'+c['id']
    line=client.get(path+'/lines',headers=headers).json()['items'][0]
    for bad_headers in ({},{'Cookie':'shiftly_account_session='+i.tokens['owner']},{'Authorization':'Bearer wrong'}):
        assert client.get(path,headers=bad_headers).status_code==401
    assert client.get(path+'/lines?missing=nonsense',headers=headers).status_code==400
    saved=client.post(path+'/lines/'+line['id'],headers=headers,json=fields(i,version=1,entry={'mode':'total','amount':'0','unit':'kg'}))
    assert saved.status_code==200,saved.text
    assert client.post(path+'/review',headers=headers,json=fields(i,version=saved.json()['count']['version'])).status_code==200
    c=client.get(path,headers=headers).json()
    final=client.post(path+'/post',headers=headers,json=fields(i,version=c['version']))
    assert final.status_code==200,final.text
    assert client.get(base+'/count-status',headers=headers).json()['lastCount']['id']==c['id']
    assert client.get(base+'/counts',headers=headers).json()['items'][0]['id']==c['id']


def test_count_and_stock_pagination_search_and_shelf_filters(inventory):
    i=inventory;_,shelves=setup_stock(i)
    shelf=shelves[0]
    for n in range(41):
        p=i.service.create_product(i.tokens['owner'],fields(i,name=f'Ingredient {n:02}',sku=f'COUNT-{n:02}',baseUnit='each'))
        live=i.service.shelf(i.tokens['owner'],shelf['id'])
        i.service.place(i.tokens['owner'],shelf['id'],p['id'],fields(i,version=live['version'],active=True))
    c=start(i)
    for reader in (lambda after:i.counts.stock(i.tokens['owner'],after=after),
                   lambda after:i.counts.lines(i.tokens['owner'],c['id'],after=after),
                   lambda after:i.counts.comparisons(i.tokens['owner'],c['id'],after=after)):
        first=reader(None);second=reader(first['nextCursor'])
        assert len(first['items'])==40 and len(second['items'])==2 and second['nextCursor'] is None
        assert [p['name'] for p in first['items']+second['items']]==[f'Ingredient {n:02}' for n in range(41)]+['White Quella']
    assert len(i.counts.stock(i.tokens['owner'],query='COUNT-40',shelf=shelf['id'])['items'])==1
    assert i.counts.stock(i.tokens['owner'],shelf='unassigned')['items']==[]
    assert len(i.counts.lines(i.tokens['owner'],c['id'],query='ingredient 40',shelf=shelf['id'])['items'])==1


def test_archiving_never_erases_a_posted_balance_and_new_listing_is_unknown(inventory):
    i=inventory;p,_=setup_stock(i);c=post(i,observe_all(i,start(i)))
    i.service.product_state(i.tokens['owner'],p['id'],fields(i,version=p['version'],active=False))
    retained=i.counts.stock(i.tokens['owner'])['items'][0]
    assert retained['quantity']=='13.25' and retained['active'] is False and retained['countId']==c['id']
    assert i.counts.stock_detail(i.tokens['owner'],p['id'])['locations']['items'][0]['quantity']=='13.25'


def test_reused_request_id_cannot_change_payload(inventory):
    i=inventory;setup_stock(i)
    body=fields(i,businessDate='2026-09-25')
    c=i.counts.start(i.tokens['owner'],body)
    assert i.counts.start(i.tokens['owner'],body)==c
    denied('conflict',lambda:i.counts.start(i.tokens['owner'],{**body,'businessDate':'2026-09-26'}))
