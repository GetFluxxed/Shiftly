"""Store-scoped physical count lifecycle; no catalog or account mutations."""
import hashlib
import json
from uuid import uuid4

import psycopg
from backend.shiftly.identity.contracts import IdentityError
from ..repository import InventoryRepository
from ..movements import MovementRepository
from .. import validation as valid
from . import validation as measured
from .repository import CountRepository, MAX_LINES, observation


def conflict(message, reason='state_conflict'):
    raise IdentityError('conflict',message,reason=reason)


def found(value):
    if value is None:
        raise IdentityError('not_found','This inventory record is unavailable in your store.')
    return value


def shelf_filter(value):
    if value in ('','unassigned'):
        return value
    return valid.identifier(value)


class CountService:
    def __init__(self, connect, accounts):
        self.connect, self.accounts = connect, accounts
        self.repository = CountRepository()
        self.audit = InventoryRepository()

    def actor(self, connection, token, capability='inventory.view', expected=None, *, writing=False):
        actor = (self.accounts.require_selected_store(token,capability,connection=connection,expected_store_id=expected)
                 if writing else self.accounts.require(token,capability,connection=connection))
        if actor.business_id is None or 'inventory.view' not in actor.capabilities:
            raise IdentityError('forbidden','Inventory access is required for this store.',reason='permission_denied')
        return actor

    def write(self, token, fields, capability, operation, payload, change):
        request_id = valid.identifier(fields.get('requestId'))
        fingerprint = hashlib.sha256(json.dumps([operation,payload],sort_keys=True,separators=(',',':')).encode()).hexdigest()
        try:
            with self.connect() as connection:
                actor = self.actor(connection,token,capability,fields.get('expectedStoreId'),writing=True)
                MovementRepository.lock_store(connection,actor)
                replay = self.audit.replay(connection,actor,request_id)
                if replay:
                    if replay[0] != fingerprint:
                        conflict('This request already describes another change. Reload before changing it.')
                    return replay[1]
                target, before, result = change(connection,actor)
                self.audit.record(connection,actor,request_id,fingerprint,operation,target,before,result,result)
                return result
        except psycopg.errors.UniqueViolation as error:
            raise IdentityError('conflict','A count is already open for this store. Reload to resume it.',reason='state_conflict') from error

    def dashboard(self, token):
        with self.connect() as connection:
            actor = self.actor(connection,token)
            return self.repository.dashboard(connection,actor)

    def start(self, token, fields):
        day = measured.business_date(fields.get('businessDate'))
        def change(connection, actor):
            if self.repository.dashboard(connection,actor)['openCount']:
                conflict('A count is already open for this store. Resume it before starting another.')
            scope = self.repository.scope(connection,actor)
            if not scope:
                conflict('Assign at least one product to a store shelf before starting a count.')
            if len(scope)>MAX_LINES:
                conflict('This store has too many count locations for a single count. Contact your administrator.')
            if any(row['base_unit'] not in ('each','g','kg') for row in scope):
                conflict('A legacy volume product needs a supported stock unit before counting. Ask the catalog administrator.')
            count_id = str(uuid4())
            self.repository.create(connection,actor,count_id,day,scope)
            return count_id,None,self.repository.summary(connection,actor,count_id)
        return self.write(token,fields,'counts.submit','count.started',day,change)

    def detail(self, token, count_id):
        count_id = valid.identifier(count_id)
        with self.connect() as connection:
            actor = self.actor(connection,token)
            count = found(self.repository.count(connection,actor,count_id))
            changed = count['state'] in ('draft','review') and count['configuration_hash'] != self.repository.fingerprint(self.repository.scope(connection,actor))
            return {**self.repository.summary(connection,actor,count_id), 'configurationChanged':changed}

    def lines(self, token, count_id, *, query='', after=None, shelf='', missing=False):
        count_id = valid.identifier(count_id)
        query,_ = valid.page(query,None)
        after = valid.product_cursor(after)
        shelf = shelf_filter(shelf)
        if type(missing) is not bool:
            valid.invalid('Choose all entries or not-counted entries.')
        with self.connect() as connection:
            actor = self.actor(connection,token)
            found(self.repository.count(connection,actor,count_id))
            return self.repository.lines(connection,actor,count_id,query,after,shelf,missing)

    def line(self, token, count_id, line_id):
        count_id,line_id = valid.identifier(count_id),valid.identifier(line_id)
        with self.connect() as connection:
            actor = self.actor(connection,token)
            found(self.repository.count(connection,actor,count_id))
            return observation(found(self.repository.line(connection,actor,count_id,line_id)))

    def save(self, token, count_id, line_id, fields):
        count_id,line_id = valid.identifier(count_id),valid.identifier(line_id)
        version = valid.version(fields.get('version'))
        def change(connection, actor):
            count = found(self.repository.count(connection,actor,count_id,lock=True))
            if count['state'] != 'draft':
                conflict('This count is no longer editable. Reload its current status.')
            line = found(self.repository.line(connection,actor,count_id,line_id))
            valid.current(line,version)
            quantity,entry = measured.measurement(fields.get('entry'),line)
            before = observation(line)
            self.repository.save_line(connection,actor,count_id,line_id,quantity,entry)
            return count_id,before,{'line':observation(self.repository.line(connection,actor,count_id,line_id)),
                                   'count':self.repository.summary(connection,actor,count_id)}
        return self.write(token,fields,'counts.submit','count.observed',[count_id,line_id,version,fields.get('entry')],change)

    def comparisons(self, token, count_id, *, query='', after=None):
        count_id = valid.identifier(count_id)
        query,_ = valid.page(query,None)
        after = valid.product_cursor(after)
        with self.connect() as connection:
            actor = self.actor(connection,token)
            found(self.repository.count(connection,actor,count_id))
            return self.repository.comparisons(connection,actor,count_id,query,after)

    def ready(self, connection, actor, count):
        if count['configuration_hash'] != self.repository.fingerprint(self.repository.scope(connection,actor)):
            conflict('Products, container references or shelves changed during this count. An approver must cancel it and start a fresh count.')
        totals = self.repository.totals(connection,actor,count['id'])
        if not totals or any(row['missing'] for row in totals):
            conflict('Count every location before submitting. Confirm zero for items with none remaining.')
        for row in totals:
            measured.bounded_total(row['quantity'])
            if (row['previous_quantity'],row['previous_count_id'],row['previous_stock_version']) != (row['current_quantity'],row['current_count_id'],row['current_stock_version']):
                conflict('Posted inventory changed since this count began. Cancel it and count against the latest inventory.')
        return totals

    def transition(self, token, count_id, action, fields):
        count_id = valid.identifier(count_id)
        version = valid.version(fields.get('version'))
        if action not in ('review','post','reopen','cancel'):
            valid.invalid('Choose a valid count action.')
        capability = 'counts.submit' if action == 'review' else 'counts.approve'
        def change(connection, actor):
            count = found(self.repository.count(connection,actor,count_id,lock=True))
            valid.current(count,version)
            allowed = {'review':('draft',),'post':('review',),'reopen':('review',),'cancel':('draft','review')}
            if count['state'] not in allowed[action]:
                conflict('This count changed state. Reload before continuing.')
            before = self.repository.summary(connection,actor,count_id)
            if action in ('review','post'):
                totals = self.ready(connection,actor,count)
            if action == 'post':
                self.repository.post(connection,actor,count,totals)
            else:
                self.repository.transition(connection,actor,count_id,{'review':'review','reopen':'draft','cancel':'cancelled'}[action])
            return count_id,before,self.repository.summary(connection,actor,count_id)
        return self.write(token,fields,capability,'count.'+action,[count_id,version],change)

    def history(self, token, *, after=None):
        after = valid.identifier(after) if after else None
        with self.connect() as connection:
            return self.repository.history(connection,self.actor(connection,token),after)

    def stock(self, token, *, query='', after=None, shelf=''):
        query,_ = valid.page(query,None)
        after = valid.product_cursor(after)
        shelf = shelf_filter(shelf)
        with self.connect() as connection:
            actor = self.actor(connection,token)
            return self.repository.stock(connection,actor,query,after,shelf)

    def stock_detail(self, token, product_id, *, after=None):
        product_id = valid.identifier(product_id)
        after = valid.identifier(after) if after else None
        with self.connect() as connection:
            actor = self.actor(connection,token)
            items = self.repository.stock(connection,actor,product_id=product_id)['items']
            item = found(items[0] if items else None)
            return {**item,'locations':self.repository.stock_locations(connection,actor,product_id,item['countId'],after) if item['countId'] else {'items':[],'nextCursor':None}}
