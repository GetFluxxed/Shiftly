from pathlib import Path
from uuid import uuid4
import shutil

import psycopg
import pytest
from backend.shiftly.runtime.migrate import migrate, MIGRATIONS


def test_native_catalog_and_shelf_flow(inventory):
    i=inventory; client=i.client; headers={'Authorization':f'Bearer {i.tokens["owner"]}'}
    def post(path,**data):
        return client.post('/api/mobile/inventory'+path,headers=headers,json={'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**data})
    p=post('/products',name='Cream',sku='001',baseUnit='kg');assert p.status_code==200,p.text
    p=p.json();s=post('/shelves',name='Walk-in shelf');assert s.status_code==200,s.text;s=s.json()
    result=post(f'/shelves/{s["id"]}/products/{p["id"]}',version=1,active=True)
    assert result.status_code==200,result.text
    read=client.get('/api/mobile/inventory/shelves/'+s['id'],headers=headers)
    assert read.status_code==200 and read.json()['products']['items']==[p]
    assert read.headers['cache-control']=='no-store'
    conflict=post('/products',name='Duplicate',sku='001',baseUnit='kg')
    assert conflict.status_code==409 and conflict.json()['errorCode']=='duplicate_identifier'
    rename=post('/products/'+p['id'],name='Heavy cream',sku='001',version=1)
    assert rename.status_code==200
    stale=post('/products/'+p['id'],name='Old',sku='001',version=1)
    assert stale.status_code==409 and stale.json()['errorCode']=='stale_record'
    assert client.get('/api/mobile/inventory/products',headers=headers,params={'q':'heavy'}).json()['items'][0]['name']=='Heavy cream'


@pytest.mark.parametrize('headers,status', [({},401),({'Cookie':'shiftly_account_session=legacy'},401),({'Authorization':'Bearer bad'},401)])
def test_inventory_never_falls_back_to_browser_credentials(inventory,headers,status):
    assert inventory.client.get('/api/mobile/inventory/products',headers=headers).status_code==status


def test_inventory_origin_body_and_error_boundaries(inventory,monkeypatch):
    i=inventory; headers={'Authorization':f'Bearer {i.tokens["owner"]}'}
    data={'requestId':str(uuid4()),'expectedStoreId':i.stores[0],'name':'Milk','sku':'0001','baseUnit':'kg'}
    path='/api/mobile/inventory/products'
    assert i.client.post(path,headers={**headers,'Origin':'https://unrelated.example'},json=data).status_code==403
    assert i.client.post(path,headers=headers,json=[]).status_code==400
    assert i.client.post(path,headers=headers,json={**data,'name':'x'*13000}).status_code==400
    assert i.client.post(path,headers=headers,json={**data,'expectedStoreId':i.stores[1]}).json()['errorCode']=='store_context_changed'
    def broken(*_): raise psycopg.OperationalError('private credentials')
    monkeypatch.setattr(i.service.repository,'products',broken)
    unavailable=i.client.get(path,headers=headers)
    assert unavailable.status_code==503 and 'private' not in unavailable.text


def test_upgrade_from_014_retains_existing_store_and_is_repeatable(empty_database,tmp_path):
    old=tmp_path/'old';old.mkdir()
    for p in MIGRATIONS.glob('*.sql'):
        if p.name < '015': shutil.copy2(p,old/p.name)
    connect=lambda:psycopg.connect(empty_database)
    assert len(migrate(connect,directory=old))==14
    with connect() as c:
        sid=c.execute("INSERT INTO stores(name,access_code_hash) VALUES('Existing store','existing') RETURNING id").fetchone()[0]
    assert migrate(connect)==['015_inventory_catalog_and_shelves.sql', '016_product_container_amounts.sql']
    assert migrate(connect)==[]
    with connect() as c:
        assert c.execute('SELECT name FROM stores WHERE id=%s',(sid,)).fetchone()[0]=='Existing store'
        assert c.execute('SELECT count(*) FROM inventory_products').fetchone()[0]==0
