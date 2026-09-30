"""Production browser contract remains identical through legacy and FastAPI hosts."""
from uuid import uuid4

from backend.shiftly.inventory.service import InventoryService
from backend.shiftly.inventory.counts.service import CountService
from database import db_connection
from tests.transport_parity.test_accounts_parity import account_http


def request_fields(api,**values):
    return {'requestId':str(uuid4()),'expectedStoreId':api.stores[0],**values}


def opening_stock(api):
    token=api.cookies['owner'].split('=',1)[1]
    inventory=InventoryService(db_connection,api.accounts);counts=CountService(db_connection,api.accounts)
    product=inventory.create_product(token,request_fields(api,name='Parity cocoa',sku='PARITY-COCOA',baseUnit='kg'))
    shelf=inventory.create_shelf(token,request_fields(api,name='Parity shelf'))
    inventory.place(token,shelf['id'],product['id'],request_fields(api,version=shelf['version'],active=True))
    count=counts.start(token,request_fields(api,businessDate='2026-09-29'))
    line=counts.lines(token,count['id'])['items'][0]
    saved=counts.save(token,count['id'],line['id'],request_fields(api,version=1,entry={'mode':'total','amount':'10','unit':'kg'}))
    reviewed=counts.transition(token,count['id'],'review',request_fields(api,version=saved['count']['version']))
    counts.transition(token,count['id'],'post',request_fields(api,version=reviewed['version']))
    return product


def test_browser_recipe_preview_confirm_and_crew_denial_match_transports(account_http):
    api=account_http;product=opening_stock(api);owner=api.cookies['owner']
    created=api.request('POST','/api/production/recipes',cookie=owner,payload=request_fields(api,name='Parity base',
        yieldAmount='8',yieldUnit='batch',instructions='Mix.',ingredients=[{'productId':product['id'],'amount':'2','unit':'kg'}]))
    assert created.status==200,created.body
    recipe=created.json()
    detail=api.request('GET','/api/production/recipes/'+recipe['id'],cookie=owner)
    assert detail.status==200 and detail.json()==recipe
    entries=[{'recipeId':recipe['id'],'revisionId':recipe['revisionId'],'batches':1}]
    preview=api.request('POST','/api/production/preview',cookie=owner,payload={'businessDate':'2026-09-29','entries':entries})
    assert preview.status==200 and preview.json()['deductions'][0]['quantity']=='2.02'
    confirmed=api.request('POST','/api/production/logs',cookie=owner,payload=request_fields(api,logId=str(uuid4()),confirmed=True,
        businessDate='2026-09-29',entries=entries))
    assert confirmed.status==200,confirmed.body
    assert confirmed.json()['state']=='confirmed' and confirmed.json()['ingredients'][0]['remaining']=='7.98'
    assert api.request('GET','/api/production/recipes',cookie=api.cookies['crew']).status==403
    assert api.request('POST','/api/production/preview',cookie=api.cookies['crew'],payload={'businessDate':'2026-09-29','entries':entries}).status==403
