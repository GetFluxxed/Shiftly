"""Deterministic boundaries for private invoice photo extraction (no live provider)."""
import base64,io,json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4
import pytest
from PIL import Image

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.receiving import ReceivingService
from backend.shiftly.inventory.receiving.photo_provider import response_value
from backend.shiftly.inventory.receiving.photo_repository import public
from backend.shiftly.inventory.receiving.photo_repository import InvoicePhotoRepository
from backend.shiftly.inventory.receiving.photo_validation import proposal,sanitized_image
from backend.shiftly.inventory.receiving.photo_worker import InvoicePhotoWorker
from backend.shiftly.inventory.receiving.photos import InvoicePhotoService

def encoded(image,kind='PNG',**save):
    target=io.BytesIO(); image.save(target,kind,**save); return base64.b64encode(target.getvalue()).decode()

def test_photo_is_reencoded_as_bounded_jpeg_without_metadata():
    value=encoded(Image.new('RGBA',(40,20),(10,20,30,128)),pnginfo=None)
    result=sanitized_image(value)
    assert result[:2]==b'\xff\xd8' and len(result)<=5*1024*1024
    with Image.open(io.BytesIO(result)) as image:
        assert image.mode=='RGB' and not image.getexif() and max(image.size)<=4096

@pytest.mark.parametrize('value',["not base64",base64.b64encode(b'not an image').decode()])
def test_photo_rejects_untrusted_or_malformed_content(value):
    with pytest.raises(ValueError):sanitized_image(value)

def test_photo_rejects_decoded_payload_over_five_mebibytes_before_decode():
    with pytest.raises(ValueError):sanitized_image(base64.b64encode(b'x'*(5*1024*1024+1)).decode())

@pytest.mark.parametrize('value',[
 {}, {'supplier':'A','invoiceNumber':'1','lines':[{'description':'x','sku':'','quantity':'nan','unit':'each'}]},
 {'supplier':'A','invoiceNumber':'1','lines':[{'description':'x','sku':'','quantity':'1','unit':'each','productId':'invented'}]},
 {'supplier':'A','invoiceNumber':'1','lines':[{'description':'','sku':'','quantity':None,'unit':''}]},
])
def test_model_output_is_strict_and_cannot_supply_catalog_ids(value):
    with pytest.raises(ValueError):proposal(value)

@pytest.mark.parametrize('quantity',['1e999999999','+1','1,000','1234567890','1.1234567890'])
def test_model_output_rejects_non_plain_or_unbounded_decimals(quantity):
    with pytest.raises(ValueError):
        proposal({'supplier':'A','invoiceNumber':'1','lines':[
            {'description':'Milk','sku':'','quantity':quantity,'unit':'each'}]})

@pytest.mark.parametrize('field,value',[('supplier','Bad\nVendor'),('invoiceNumber','A\x001')])
def test_model_output_rejects_control_characters(field,value):
    payload={'supplier':'Vendor','invoiceNumber':'1','lines':[]}
    payload[field]=value
    with pytest.raises(ValueError):proposal(payload)

def envelope(output, **values):
    return {'status':'completed','error':None,'incomplete_details':None,'output':output,**values}

def message(text='{"supplier":"A","invoiceNumber":"1","lines":[]}'):
    return {'type':'message','role':'assistant','status':'completed',
            'content':[{'type':'output_text','text':text}]}

def test_provider_envelope_accepts_reasoning_and_one_completed_message():
    assert response_value(envelope([{'type':'reasoning','summary':[]},message()]))['supplier']=='A'

@pytest.mark.parametrize('payload',[
    envelope([message(),message()]),
    envelope([{'type':'function_call','name':'tool'},message()]),
    envelope([{'type':'message','role':'assistant','status':'completed','content':[{'type':'refusal','refusal':'no'}]}]),
    envelope([message()],incomplete_details={'reason':'max_output_tokens'}),
    envelope([{'type':'message','role':'assistant','status':'in_progress','content':[{'type':'output_text','text':'{}'}]}]),
])
def test_provider_envelope_rejects_refusal_tools_incomplete_or_mixed_output(payload):
    with pytest.raises(RuntimeError):response_value(payload)

def test_public_result_only_offers_retry_for_live_nonterminal_failure():
    row={'id':uuid4(),'state':'failed','message':'failed','proposal':None,'job_terminal':False,
         'job_attempts':1,'image_bytes':b'private','image_expires_at':2,'database_now':1}
    assert public(row)['canRetry'] is True
    for change in ({'job_terminal':True},{'job_attempts':3},{'image_bytes':None},{'image_expires_at':0},{'state':'ready'}):
        assert public({**row,**change})['canRetry'] is False

class MemoryRepository:
    def __init__(self,authorized=True):self.authority=authorized;self.completed=[];self.failed=[]
    def claim(self,c):return ({'id':'p','image_bytes':b'private','invoice_version':1,'model':'queued-model'},'lease',1)
    def authorized(self,c,row):return self.authority
    def complete(self,c,pid,token,result):self.completed.append(result);return True
    def fail(self,c,*args):self.failed.append(args);return True

class Connection:
    def __enter__(self):return self
    def __exit__(self,*args):pass

def test_worker_rechecks_fresh_authority_before_dispatch():
    calls=[]
    def provider(image, *, model):calls.append((image,model))
    worker=InvoicePhotoWorker(lambda:Connection(),provider,model='current-model')
    worker.repository=MemoryRepository(False)
    assert worker.run_one() is False and calls==[] and worker.repository.failed

def test_worker_validates_mocked_provider_and_only_stores_proposal():
    raw={'supplier':'Vendor','invoiceNumber':'001','lines':[{'description':'Milk','sku':'0007','quantity':'2','unit':'each'}]}
    called=[]
    def provider(image, *, model):
        called.append((image,model)); return raw
    worker=InvoicePhotoWorker(lambda:Connection(),provider,model='current-model'); worker.repository=MemoryRepository()
    assert worker.run_one() is True and worker.repository.completed==[raw]
    assert called==[(b'private','queued-model')]

def write_fields(i, **values):
    return {'requestId':str(uuid4()),'expectedStoreId':i.stores[0],**values}

def test_upload_authorizes_before_decode_and_rejects_unavailable_provider(inventory):
    receiving=ReceivingService(inventory.connect,inventory.accounts)
    draft=receiving.create(inventory.tokens['owner'],write_fields(inventory,supplier='A',invoiceNumber='1'))
    service=InvoicePhotoService(inventory.connect,inventory.accounts,model='test',provider_available=True)
    bad=write_fields(inventory,version=draft['version'],imageBase64='not base64')
    with pytest.raises(IdentityError) as caught:service.upload(inventory.tokens['crew'],draft['id'],bad)
    assert caught.value.code=='forbidden'
    unavailable=InvoicePhotoService(inventory.connect,inventory.accounts,model='test',provider_available=False)
    with pytest.raises(IdentityError):unavailable.upload(inventory.tokens['owner'],draft['id'],bad)
    with inventory.connect() as connection:
        assert connection.execute('SELECT count(*) FROM inventory_invoice_photos').fetchone()[0]==0

def test_replays_return_recorded_photo_and_duplicate_bypasses_serialized_daily_cap(inventory):
    receiving=ReceivingService(inventory.connect,inventory.accounts)
    draft=receiving.create(inventory.tokens['owner'],write_fields(inventory,supplier='B',invoiceNumber='2'))
    service=InvoicePhotoService(inventory.connect,inventory.accounts,model='test')
    images=[encoded(Image.new('RGB',(4,4),(index*20,0,0)),'JPEG') for index in range(10)]
    requests=[write_fields(inventory,version=1,imageBase64=value) for value in images]
    first=service.upload(inventory.tokens['owner'],draft['id'],requests[0])
    for request in requests[1:]:service.upload(inventory.tokens['owner'],draft['id'],request)
    with pytest.raises(IdentityError):
        service.upload(inventory.tokens['owner'],draft['id'],write_fields(
            inventory,version=1,imageBase64=encoded(Image.new('RGB',(4,4),(250,0,0)),'JPEG')))
    duplicate=service.upload(inventory.tokens['owner'],draft['id'],write_fields(
        inventory,version=1,imageBase64=images[0]))
    assert duplicate['id']==first['id']
    replay=service.upload(inventory.tokens['owner'],draft['id'],requests[0])
    assert replay['id']==first['id']

def test_retry_replay_returns_original_photo_after_newer_upload(inventory):
    receiving=ReceivingService(inventory.connect,inventory.accounts)
    draft=receiving.create(inventory.tokens['owner'],write_fields(inventory,supplier='C',invoiceNumber='3'))
    service=InvoicePhotoService(inventory.connect,inventory.accounts,model='test')
    first=service.upload(inventory.tokens['owner'],draft['id'],write_fields(
        inventory,version=1,imageBase64=encoded(Image.new('RGB',(5,5),'red'),'JPEG')))
    with inventory.connect() as connection:
        connection.execute("UPDATE inventory_invoice_photos SET state='failed',message='failed' WHERE id=%s",(first['id'],))
        connection.execute("UPDATE inventory_invoice_photo_jobs SET state='failed',terminal=false WHERE photo_id=%s",(first['id'],))
    retry=write_fields(inventory,version=1)
    retried=service.retry(inventory.tokens['owner'],draft['id'],retry)
    assert retried['id']==first['id']
    second=service.upload(inventory.tokens['owner'],draft['id'],write_fields(
        inventory,version=1,imageBase64=encoded(Image.new('RGB',(5,5),'blue'),'JPEG')))
    assert second['id']!=first['id']
    receiving.edit(inventory.tokens['owner'],draft['id'],write_fields(
        inventory,version=1,supplier='C updated',invoiceNumber='3',lines=[]))
    assert service.retry(inventory.tokens['owner'],draft['id'],retry)['id']==first['id']

def test_catalog_suggestions_never_return_archived_package(inventory):
    product=inventory.service.create_product(inventory.tokens['owner'],write_fields(
        inventory,name='Worker Milk',sku='MILK-1',baseUnit='kg',containerAmount='6'))
    package=next(item for item in inventory.service.packages(
        inventory.tokens['owner'],product['id'])['items'] if item['isDefault'])
    inventory.service.package_state(inventory.tokens['owner'],product['id'],package['id'],write_fields(
        inventory,version=package['version'],active=False))
    with inventory.connect() as connection:
        matches=InvoicePhotoRepository().matches(connection,inventory.companies[0],{
            'lines':[{'description':'Worker Milk','sku':'MILK-1','quantity':'1','unit':'package'}]})
    assert matches[('MILK-1','Worker Milk')]==(product['id'],None)

def test_concurrent_invoice_save_and_photo_upload_share_lock_order(inventory):
    receiving=ReceivingService(inventory.connect,inventory.accounts)
    draft=receiving.create(inventory.tokens['owner'],write_fields(
        inventory,supplier='Concurrent',invoiceNumber='LOCK-1'))
    photos=InvoicePhotoService(inventory.connect,inventory.accounts,model='test')
    gate=Barrier(2)
    image=encoded(Image.new('RGB',(10,10),'green'),'JPEG')

    def save():
        gate.wait()
        return receiving.edit(inventory.tokens['owner'],draft['id'],write_fields(
            inventory,version=1,supplier='Concurrent saved',invoiceNumber='LOCK-1',lines=[]))

    def upload():
        gate.wait()
        try:
            return photos.upload(inventory.tokens['owner'],draft['id'],write_fields(
                inventory,version=1,imageBase64=image))['state']
        except IdentityError as error:
            return error.reason

    with ThreadPoolExecutor(2) as pool:
        saved=pool.submit(save)
        uploaded=pool.submit(upload)
        assert saved.result(timeout=5)['supplier']=='Concurrent saved'
        assert uploaded.result(timeout=5) in {'queued','stale_record'}
