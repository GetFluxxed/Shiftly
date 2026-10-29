from decimal import Decimal, localcontext
from uuid import uuid4

import psycopg

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.movements import MovementRepository
from backend.shiftly.inventory.validation import identifier, version, product_cursor
from .repository import ProductionRepository, decimal
from . import validation as valid


def conflict(message, reason='state_conflict'):
    raise IdentityError('conflict',message,reason=reason)


def found(value,message='This production record is unavailable.'):
    if value is None: raise IdentityError('not_found',message)
    return value


class ProductionService:
    def __init__(self,connect,accounts,forecast_enqueue=None):
        self.connect,self.accounts=connect,accounts
        self.repository=ProductionRepository(); self.movements=MovementRepository()
        self.forecast_enqueue=forecast_enqueue

    def actor(self,connection,token,capability='production.view',expected=None,*,writing=False):
        actor=(self.accounts.require_selected_store(token,capability,connection=connection,expected_store_id=expected)
               if writing else self.accounts.require(token,capability,connection=connection))
        if actor.business_id is None or 'production.view' not in actor.capabilities:
            raise IdentityError('forbidden','Production access is required.',reason='permission_denied')
        return actor

    def recipes(self,token,*,query='',after=None):
        if not isinstance(query,str) or len(query)>160: valid.invalid('Search must be text of at most 160 characters.')
        after=product_cursor(after)
        with self.connect() as connection:return self.repository.recipes(connection,self.actor(connection,token),query.strip(),after)

    def recipe(self,token,recipe_id):
        with self.connect() as connection:return found(self.repository.recipe(connection,self.actor(connection,token),identifier(recipe_id)))

    def _write_request(self,connection,actor,fields,operation,payload,change):
        request_id=identifier(fields.get('requestId')); fingerprint=valid.fingerprint(operation,payload)
        replay=self.repository.request(connection,actor,request_id)
        if replay:
            if replay['fingerprint']!=fingerprint: conflict('This request already describes another change. Reload before changing it.')
            return replay['result']
        result=change()
        self.repository.record_request(connection,actor,request_id,fingerprint,result)
        return result

    def create_recipe(self,token,fields):
        data=valid.recipe_input(fields)
        with self.connect() as connection:
            actor=self.actor(connection,token,'recipes.manage',fields.get('expectedStoreId'),writing=True)
            def change():
                products=self.repository.products(connection,actor,[i['productId'] for i in data['ingredients']])
                if len(products)!=len(data['ingredients']): conflict('Every ingredient must be an active product in this business.')
                for item in data['ingredients']:
                    item['baseAmount']=valid.convert(item['amount'],item['unit'],products[item['productId']]['base_unit'])
                recipe_id,revision_id=str(uuid4()),str(uuid4())
                self.repository.create_recipe(connection,actor,recipe_id,revision_id,data,products)
                return self.repository.recipe(connection,actor,recipe_id)
            return self._write_request(connection,actor,fields,'recipe.created',data,change)

    def edit_recipe(self,token,recipe_id,fields):
        recipe_id=identifier(recipe_id); expected=version(fields.get('version')); data=valid.recipe_input(fields)
        with self.connect() as connection:
            actor=self.actor(connection,token,'recipes.manage',fields.get('expectedStoreId'),writing=True)
            def change():
                current=found(self.repository.recipe(connection,actor,recipe_id,lock=True))
                if current['version']!=expected: conflict('This recipe changed. Reload the latest version before saving.','stale_record')
                products=self.repository.products(connection,actor,[i['productId'] for i in data['ingredients']])
                if len(products)!=len(data['ingredients']): conflict('Every ingredient must be an active product in this business.')
                for item in data['ingredients']:
                    item['baseAmount']=valid.convert(item['amount'],item['unit'],products[item['productId']]['base_unit'])
                self.repository.revise_recipe(connection,actor,recipe_id,str(uuid4()),current['version'],data,products)
                return self.repository.recipe(connection,actor,recipe_id)
            return self._write_request(connection,actor,fields,'recipe.revised',[recipe_id,expected,data],change)

    def _calculate(self,connection,actor,entry_fields,balances,active_products):
        snapshots=[]; aggregate={}
        with localcontext() as context:
            context.prec=50
            for requested in entry_fields:
                recipe=self.repository.recipe(connection,actor,requested['recipeId'],requested['revisionId'],current_only=True)
                if recipe is None:
                    if self.repository.recipe(connection,actor,requested['recipeId'],requested['revisionId']):
                        conflict('This recipe changed. Reload its current revision before recording production.','stale_record')
                    raise IdentityError('not_found','This recipe revision is unavailable.')
                snapshots.append({'recipeId':recipe['id'],'revisionId':recipe['revisionId'],'name':recipe['name'],
                                  'yieldAmount':recipe['yieldAmount'],'yieldUnit':recipe['yieldUnit'],'batches':requested['batches']})
                for ingredient in recipe['ingredients']:
                    key=ingredient['productId']; item=aggregate.setdefault(key,{**ingredient,'recipeAmount':Decimal(0)})
                    contribution=valid.exact(Decimal(ingredient['baseAmount'])*requested['batches'],'Recipe quantity')
                    item['recipeAmount']=valid.exact(item['recipeAmount']+contribution,'Recipe quantity')
        deductions=[];issues=[]
        if len(aggregate)>500:
            valid.invalid('A production submission may reference at most 500 unique ingredients.')
        with localcontext() as context:
            context.prec=50
            for product_id,item in aggregate.items():
                recipe_amount=valid.exact(item['recipeAmount'],'Recipe quantity')
                allowance=valid.exact(recipe_amount*Decimal('0.01'),'One percent ingredient allowance')
                quantity=valid.exact(recipe_amount+allowance,'Production deduction')
                balance=balances.get(product_id)
                remaining=balance['quantity']-quantity if balance else None
                issue=None
                if product_id not in active_products: issue=('unknown_stock','This ingredient is no longer active at the selected store.')
                elif balance is None: issue=('unknown_stock','Complete an opening inventory count for this ingredient.')
                elif balance['base_unit']!=item['baseUnit']: issue=('unit_changed','The ingredient stock unit changed. Reload the recipe.')
                elif remaining<0: issue=('insufficient_stock','There is not enough stock for this production entry.')
                if issue:issues.append({'productId':product_id,'code':issue[0],'message':issue[1]})
                deductions.append({'productId':product_id,'name':item['name'],'sku':item['sku'],'baseUnit':item['baseUnit'],
                                   'recipeAmount':recipe_amount,'allowanceAmount':allowance,'quantity':quantity,
                                   'balance':balance['quantity'] if balance else None,'remaining':remaining,
                                   'countId':balance['count_id'] if balance else None})
        return snapshots,deductions,issues

    @staticmethod
    def _preview(deductions,issues):
        return {'deductions':[{k:(decimal(v) if k in ('recipeAmount','allowanceAmount','quantity','balance','remaining') else v)
                               for k,v in item.items() if k not in ('countId','sku')} for item in deductions],
                'canConfirm':not issues,'issues':issues}

    def preview(self,token,fields):
        day=valid.business_date(fields.get('businessDate')); entries=valid.entries(fields.get('entries'))
        with self.connect() as connection:
            actor=self.actor(connection,token)
            revisions=[self.repository.recipe(connection,actor,e['recipeId'],e['revisionId']) for e in entries]
            product_ids=[i['productId'] for r in revisions if r for i in r['ingredients']]
            active=self.repository.active_products(connection,actor,product_ids)
            snapshots,deductions,issues=self._calculate(connection,actor,entries,self.movements.balances(connection,actor,product_ids),active)
            return {'businessDate':day.isoformat(),'entries':snapshots,**self._preview(deductions,issues)}

    def confirm(self,token,fields):
        log_id=identifier(fields.get('logId')); request_id=identifier(fields.get('requestId'))
        if fields.get('confirmed') is not True: valid.invalid('Production must be explicitly confirmed.')
        day=valid.business_date(fields.get('businessDate')); entries=valid.entries(fields.get('entries'))
        payload=[log_id,day,entries]; payload_fingerprint=valid.fingerprint('production.confirmed',payload)
        try:
            with self.connect() as connection:
                actor=self.actor(connection,token,'production.submit',fields.get('expectedStoreId'),writing=True)
                self.movements.lock_store(connection,actor)
                existing=self.repository.log_by_id(connection,actor,log_id,lock=True)
                if existing:
                    if existing['payload_fingerprint']!=payload_fingerprint: conflict('This production log ID already describes another submission.')
                    return self.repository.log(connection,actor,log_id)
                replay=self.repository.request(connection,actor,request_id)
                if replay:
                    if replay['fingerprint']!=payload_fingerprint: conflict('This request already describes another change. Reload before changing it.')
                    return replay['result']
                revisions=[found(self.repository.recipe(connection,actor,e['recipeId'],e['revisionId']),'This recipe revision is unavailable.') for e in entries]
                product_ids=[i['productId'] for r in revisions for i in r['ingredients']]
                active=self.repository.active_products(connection,actor,product_ids)
                snapshots,deductions,issues=self._calculate(connection,actor,entries,self.movements.balances(connection,actor,product_ids),active)
                if issues: conflict('Production cannot be confirmed until its inventory issues are resolved.')
                for item in deductions:
                    item['movementId']=self.movements.apply(connection,actor,product_id=item['productId'],base_unit=item['baseUnit'],
                        quantity_after=item['remaining'],kind='production',source_id=log_id)
                self.repository.create_log(connection,actor,log_id,day,payload_fingerprint,snapshots,deductions)
                result=self.repository.log(connection,actor,log_id)
                self.repository.record_request(connection,actor,request_id,payload_fingerprint,result)
                if self.forecast_enqueue is not None:
                    self.forecast_enqueue(connection,actor,log_id)
                return result
        except psycopg.errors.UniqueViolation as error:
            # A concurrent actor may have committed the same client-generated log
            # ID while this transaction waited on a unique constraint.
            with self.connect() as connection:
                actor=self.actor(connection,token,'production.submit',fields.get('expectedStoreId'),writing=True)
                existing=self.repository.log_by_id(connection,actor,log_id)
                if existing and existing['payload_fingerprint']==payload_fingerprint:
                    return self.repository.log(connection,actor,log_id)
            conflict('This production submission conflicts with an existing record.')

    def logs(self,token,*,after=None):
        after=identifier(after) if after else None
        with self.connect() as connection:return self.repository.logs(connection,self.actor(connection,token),after)

    def log(self,token,log_id):
        with self.connect() as connection:return found(self.repository.log(connection,self.actor(connection,token),identifier(log_id)))

    def reverse(self,token,log_id,fields):
        log_id=identifier(log_id); reason=valid.text(fields.get('reason'),'Reversal reason',500)
        with self.connect() as connection:
            actor=self.actor(connection,token,'production.manage',fields.get('expectedStoreId'),writing=True)
            self.movements.lock_store(connection,actor)
            def change():
                header=found(self.repository.log_by_id(connection,actor,log_id,lock=True))
                if header['state']!='confirmed': conflict('This production log has already been reversed.')
                ingredients=self.repository.reversal_rows(connection,log_id)
                balances=self.movements.balances(connection,actor,[r['product_id'] for r in ingredients])
                for row in ingredients:
                    balance=balances.get(str(row['product_id']))
                    if not balance or balance['count_id']!=row['count_id']:
                        conflict('A physical count superseded this production entry, so it cannot be reversed.')
                for row in ingredients:
                    balance=balances[str(row['product_id'])]
                    self.movements.apply(connection,actor,product_id=str(row['product_id']),base_unit=row['base_unit'],
                        quantity_after=balance['quantity']+row['quantity'],kind='reversal',source_id=log_id,reverses_id=str(row['movement_id']))
                self.repository.reverse(connection,actor,log_id,reason)
                return self.repository.log(connection,actor,log_id)
            return self._write_request(connection,actor,fields,'production.reversed',[log_id,reason],change)
