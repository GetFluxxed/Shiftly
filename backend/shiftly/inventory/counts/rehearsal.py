"""Synthetic stock evidence included in the existing release backup rehearsal."""
from uuid import uuid4

from backend.shiftly.identity.accounts import AccountsService
from ..service import InventoryService
from .service import CountService


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
    # Preserve both posted evidence and a distinct resumable draft in the archive.
    draft=counts.start(token,fields(businessDate='2026-09-26'))
    return {'productId':product['id'],'countId':posted['id'],'draftId':draft['id']}


def verify_count(connect, token, expected):
    counts=CountService(connect,AccountsService(connect))
    item=counts.stock_detail(token,expected['productId'])
    if item['quantity']!='13.25' or item['countId']!=expected['countId']:
        raise RuntimeError('Restored inventory differs from the finalized count.')
    entry=item['locations']['items'][0]['entry']
    if entry!={'mode':'containers','fullContainers':2,'partialAmount':'1250','partialUnit':'g'}:
        raise RuntimeError('Restored original count observation changed.')
    draft=counts.detail(token,expected['draftId'])
    if draft['state']!='draft' or draft['countedLines']!=0:
        raise RuntimeError('Restored inventory draft cannot be resumed.')
