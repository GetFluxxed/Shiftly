"""Authorized, bounded advisory forecast snapshots; provider work stays in workers."""
import hashlib
import json
from uuid import uuid4

from backend.shiftly.identity.contracts import IdentityError
from backend.shiftly.inventory.validation import identifier
from .repository import ForecastRepository

PROMPT_VERSION = 'production-forecast-v1'
REQUIRED = {'forecasts.view','reports.view','production.view','inventory.view'}


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',',':'), default=str).encode()


class ForecastService:
    def __init__(self, connect, accounts, *, model, provider_available=True):
        self.connect,self.accounts,self.model = connect,accounts,model
        self.provider_available=provider_available
        self.repository=ForecastRepository()

    def _actor(self, connection, token, expected=None, *, writing=False):
        actor=(self.accounts.require_selected_store(token,'forecasts.view',connection=connection,expected_store_id=expected)
               if writing else self.accounts.require(token,'forecasts.view',connection=connection))
        if actor.business_id is None or not REQUIRED.issubset(actor.capabilities):
            raise IdentityError('forbidden','Forecast access requires reports, production and inventory access.',reason='permission_denied')
        return actor

    def _snapshot(self, connection, actor, log_id=None):
        if log_id is not None:
            log_id=identifier(log_id)
            exists=connection.execute('SELECT 1 FROM production_logs WHERE business_id=%s AND store_id=%s AND id=%s',
                                      (actor.business_id,actor.store_id,log_id)).fetchone()
            if not exists: raise IdentityError('not_found','This production record is unavailable.')
        facts,coverage,source,as_of=self.repository.sources(connection,actor,log_id)
        raw=encoded([actor.business_id,actor.store_id,log_id,PROMPT_VERSION,self.model,source])
        while len(raw)>79000:
            source['coverage']['truncated']=True
            if source['productionDeductions']:
                source['productionDeductions'].pop()
            elif source['productionEntries']:
                source['productionEntries'].pop()
            elif source['shiftReports']:
                source['shiftReports'].pop()
            elif source['recipes']:
                source['recipes'].pop()
            elif source['stockAsOf'] or facts['ingredients']:
                if source['stockAsOf']: source['stockAsOf'].pop()
                if facts['ingredients']: facts['ingredients'].pop()
            elif facts['daily']:
                facts['daily'].pop()
            else:
                raise RuntimeError('Forecast source could not be bounded.')
            raw=encoded([actor.business_id,actor.store_id,log_id,PROMPT_VERSION,self.model,source])
        source['included']={key:len(source[key]) for key in (
            'recipes','productionEntries','productionDeductions','stockAsOf','shiftReports')}
        source['included'].update(daily=len(facts['daily']),ingredients=len(facts['ingredients']))
        raw=encoded([actor.business_id,actor.store_id,log_id,PROMPT_VERSION,self.model,source])
        if len(raw)>80000: raise RuntimeError('Forecast source could not be bounded.')
        return facts,coverage,source,as_of,hashlib.sha256(raw).hexdigest()

    def enqueue_after_confirmation(self, connection, actor, log_id):
        facts,coverage,source,_,fingerprint=self._snapshot(connection,actor,None)
        source['coverage']=coverage
        return self.repository.enqueue(connection,actor,forecast_id=str(uuid4()),log_id=None,
            fingerprint=fingerprint,prompt_version=PROMPT_VERSION,model=self.model,facts=facts,source=source)

    def generate(self, token, fields):
        request_id=identifier(fields.get('requestId')); log_id=fields.get('logId')
        if log_id is not None: log_id=identifier(log_id)
        with self.connect() as connection:
            actor=self._actor(connection,token,fields.get('expectedStoreId'),writing=True)
            request_fp=hashlib.sha256(encoded(['forecast.generate',log_id])).hexdigest()
            replay=self.repository.replay(connection,actor,request_id)
            if replay:
                if replay[0]!=request_fp:
                    raise IdentityError('conflict','This request was already used for another forecast.',reason='state_conflict')
                row=self.repository.one(connection,actor,str(replay[1]))
                return self._render(connection,actor,row,log_id)
            facts,coverage,source,_,fingerprint=self._snapshot(connection,actor,log_id)
            source['coverage']=coverage
            forecast_id=self.repository.enqueue(connection,actor,forecast_id=str(uuid4()),log_id=log_id,
                fingerprint=fingerprint,prompt_version=PROMPT_VERSION,model=self.model,facts=facts,source=source,
                retry_terminal=True)
            self.repository.record_request(connection,actor,request_id,request_fp,forecast_id)
            return self._render(connection,actor,self.repository.one(connection,actor,forecast_id),log_id)

    def get(self, token, *, log_id=None):
        with self.connect() as connection:
            actor=self._actor(connection,token)
            if log_id is not None: identifier(log_id)
            row=self.repository.latest(connection,actor,log_id)
            if row is None:
                return self._empty(actor.store_id,'unavailable' if not self.provider_available else 'not_requested')
            return self._render(connection,actor,row,log_id)

    def _empty(self, store_id, status):
        return {'storeId':store_id,'status':status,'forecast':None,
                'error':'Forecast generation is not configured.' if status=='unavailable' else None}

    def _render(self, connection, actor, row, log_id):
        if row is None:return self._empty(actor.store_id,'not_requested')
        _,_,_,_,current=self._snapshot(connection,actor,log_id)
        source=row['source_snapshot']; coverage=source['coverage']
        status=row['status'] if self.provider_available else 'unavailable'
        error=('Forecast generation is not configured.' if status=='unavailable' else row['error'])
        return {'storeId':actor.store_id,'status':status,'error':error,'forecast':{
            'id':str(row['id']),'logId':str(row['log_id']) if row['log_id'] else None,
            'asOf':source['snapshotDate'],
            'generatedAt':row['generated_at'].isoformat() if row['generated_at'] else None,
            'model':row['model'],'stale':current!=row['source_fingerprint'],'coverage':coverage,
            'facts':row['facts'],'analysis':row['analysis'] if status=='ready' else None}}
