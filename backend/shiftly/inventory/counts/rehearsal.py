"""Synthetic stock evidence included in the existing release backup rehearsal."""
from uuid import uuid4

from backend.shiftly.identity.accounts import AccountsService
from ..service import InventoryService
from .service import CountService
from backend.shiftly.production import ProductionService


def seed_count(connect, token):
    accounts=AccountsService(connect)
    catalog=InventoryService(connect,accounts)
    counts=CountService(connect,accounts)
    actor=accounts.resolve_actor(token)
    def fields(**values):return {'requestId':str(uuid4()),'expectedStoreId':actor.store_id,**values}
    product=catalog.create_product(token,fields(name='Rehearsal Quella',sku='REHEARSAL-COUNT',baseUnit='kg',containerAmount='6'))
    shelf=catalog.create_shelf(token,fields(name='Rehearsal shelf'))
    catalog.place(token,shelf['id'],product['id'],fields(version=shelf['version'],active=True))
    count=counts.start(token,fields(businessDate='2026-09-25'))
    line=counts.lines(token,count['id'])['items'][0]
    count=counts.save(token,count['id'],line['id'],fields(version=line['version'],entry={
        'mode':'containers','fullContainers':2,'partialAmount':'1250','partialUnit':'g'}))['count']
    count=counts.transition(token,count['id'],'review',fields(version=count['version']))
    post_fields=fields(version=count['version'])
    posted=counts.transition(token,count['id'],'post',post_fields)
    assert counts.transition(token,count['id'],'post',post_fields)==posted
    production=ProductionService(connect,accounts)
    recipe_fields=dict(name='Rehearsal flavor',yieldAmount='3',yieldUnit='kg',instructions='Synthetic recovery fixture.',
        ingredients=[{'productId':product['id'],'amount':'1','unit':'kg'}])
    recipe=production.create_recipe(token,fields(**recipe_fields))
    entries=[{'recipeId':recipe['id'],'revisionId':recipe['revisionId'],'batches':1}]
    reversed_log=production.confirm(token,fields(logId=str(uuid4()),businessDate='2026-09-25',entries=entries,confirmed=True))
    production.reverse(token,reversed_log['id'],fields(reason='Rehearsal correction'))
    log=production.confirm(token,fields(logId=str(uuid4()),businessDate='2026-09-25',entries=entries,confirmed=True))
    production.edit_recipe(token,recipe['id'],fields(**{**recipe_fields,'name':'Revised rehearsal flavor','version':recipe['version']}))
    # Preserve posted count, revised recipe, original production and a resumable draft.
    draft=counts.start(token,fields(businessDate='2026-09-26'))
    return {'productId':product['id'],'countId':posted['id'],'draftId':draft['id'],
            'recipeId':recipe['id'],'logId':log['id'],'reversedLogId':reversed_log['id']}


def verify_count(connect, token, expected):
    counts=CountService(connect,AccountsService(connect))
    item=counts.stock_detail(token,expected['productId'])
    if item['quantity']!='12.24' or item['countId']!=expected['countId'] or item['stockVersion']!=4:
        raise RuntimeError('Restored running inventory differs from the count and production history.')
    entry=item['locations']['items'][0]['entry']
    if entry!={'mode':'containers','fullContainers':2,'partialAmount':'1250','partialUnit':'g'}:
        raise RuntimeError('Restored original count observation changed.')
    draft=counts.detail(token,expected['draftId'])
    if draft['state']!='draft' or draft['countedLines']!=0:
        raise RuntimeError('Restored inventory draft cannot be resumed.')

    production=ProductionService(connect,AccountsService(connect))
    log=production.log(token,expected['logId'])
    reversed_log=production.log(token,expected['reversedLogId'])
    recipe=production.recipe(token,expected['recipeId'])
    if (log['state']!='confirmed' or log['ingredients'][0]['quantity']!='1.01'
            or log['entries'][0]['name']!='Rehearsal flavor' or reversed_log['state']!='reversed'
            or recipe['name']!='Revised rehearsal flavor' or recipe['version']!=2):
        raise RuntimeError('Restored recipe, production deduction or reversal evidence changed.')
