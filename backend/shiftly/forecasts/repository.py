"""Store-scoped forecast snapshots and leased queue SQL."""
from datetime import date
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.shiftly.inventory.quantities import decimal_text


def rows(connection, sql, parameters=()):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(sql, parameters)
        return cursor.fetchall()


class ForecastRepository:
    def sources(self, connection, actor, log_id=None):
        scope = (actor.business_id, actor.store_id)
        daily = rows(connection, '''SELECT l.business_date AS date,e.recipe_id,e.name,SUM(e.batches) AS batches
            FROM production_logs l JOIN production_log_entries e ON e.log_id=l.id
            WHERE l.business_id=%s AND l.store_id=%s AND l.state='confirmed'
              AND l.business_date BETWEEN CURRENT_DATE-27 AND CURRENT_DATE
            GROUP BY l.business_date,e.recipe_id,e.name ORDER BY l.business_date DESC,e.recipe_id LIMIT 201''', scope)
        ingredients = rows(connection, '''WITH usage AS (
              SELECT i.product_id,SUM(i.quantity) used_amount FROM production_logs l
              JOIN production_log_ingredients i ON i.log_id=l.id
              WHERE l.business_id=%s AND l.store_id=%s AND l.state='confirmed'
                AND l.business_date BETWEEN CURRENT_DATE-27 AND CURRENT_DATE GROUP BY i.product_id)
            SELECT p.id product_id,p.name,p.base_unit,COALESCE(u.used_amount,0) used_amount,
              b.quantity,b.last_counted_at,b.updated_at,b.version
            FROM inventory_store_products sp JOIN inventory_products p ON p.business_id=sp.business_id AND p.id=sp.product_id
            LEFT JOIN usage u ON u.product_id=p.id LEFT JOIN inventory_stock_balances b
              ON b.business_id=sp.business_id AND b.store_id=sp.store_id AND b.product_id=sp.product_id
            WHERE sp.business_id=%s AND sp.store_id=%s AND sp.active AND p.active
            ORDER BY inventory_key(p.name),p.id LIMIT 501''', (*scope,actor.business_id,actor.store_id))
        recipes = rows(connection, '''SELECT r.id,r.version,v.name,v.id revision_id,v.yield_amount,v.yield_unit,
              jsonb_agg(jsonb_build_object('productId',i.product_id,'name',i.name,'baseUnit',i.base_unit,
                'baseAmount',i.base_amount::text) ORDER BY i.product_id) ingredients,
              bool_and(p.active AND EXISTS (SELECT 1 FROM inventory_store_products listed
                WHERE listed.business_id=i.business_id AND listed.product_id=i.product_id
                  AND listed.store_id=%s AND listed.active)) active
            FROM production_recipes r JOIN production_recipe_revisions v ON v.id=r.current_revision_id
            JOIN production_recipe_ingredients i ON i.revision_id=v.id
            JOIN inventory_products p ON p.business_id=i.business_id AND p.id=i.product_id
            WHERE r.business_id=%s AND EXISTS (SELECT 1 FROM production_recipe_ingredients relevant
              JOIN inventory_store_products listed ON listed.business_id=relevant.business_id
                AND listed.product_id=relevant.product_id AND listed.store_id=%s AND listed.active
              WHERE relevant.revision_id=v.id)
            GROUP BY r.id,v.id ORDER BY inventory_key(v.name),r.id LIMIT 101''',
            (actor.store_id,actor.business_id,actor.store_id))
        entries = rows(connection, '''SELECT l.id log_id,l.business_date,e.sequence,e.recipe_id,e.revision_id,e.name,
              e.yield_amount,e.yield_unit,e.batches
            FROM production_logs l JOIN production_log_entries e ON e.log_id=l.id
            WHERE l.business_id=%s AND l.store_id=%s AND l.state='confirmed'
              AND l.business_date BETWEEN CURRENT_DATE-27 AND CURRENT_DATE
            ORDER BY l.business_date DESC,l.id DESC,e.sequence LIMIT 201''', scope)
        deductions = rows(connection, '''SELECT l.id log_id,l.business_date,i.product_id,i.name,i.base_unit,
              i.recipe_amount,i.allowance_amount,i.quantity
            FROM production_logs l JOIN production_log_ingredients i ON i.log_id=l.id
            WHERE l.business_id=%s AND l.store_id=%s AND l.state='confirmed'
              AND l.business_date BETWEEN CURRENT_DATE-27 AND CURRENT_DATE
            ORDER BY l.business_date DESC,l.id DESC,i.product_id LIMIT 501''', scope)
        reports = rows(connection, '''SELECT id,shift,notes,created_at FROM reports
            WHERE store_id=%s AND created_at>=NOW()-INTERVAL '28 days'
            ORDER BY created_at DESC,id DESC LIMIT 51''', (actor.store_id,))
        log_count = connection.execute('''SELECT count(*),count(DISTINCT business_date),max(business_date)
            FROM production_logs WHERE business_id=%s AND store_id=%s AND state='confirmed'
              AND business_date BETWEEN CURRENT_DATE-27 AND CURRENT_DATE''', scope).fetchone()
        facts = {
            'daily': [{'date': r['date'].isoformat(), 'recipeId': str(r['recipe_id']), 'name': r['name'],
                       'batches': int(r['batches'])} for r in daily[:200]],
            'ingredients': [{'productId': str(r['product_id']), 'name': r['name'], 'baseUnit': r['base_unit'],
                             'quantity': decimal_text(r['quantity']) if r['quantity'] is not None else None,
                             'usedAmount': decimal_text(r['used_amount'])} for r in ingredients[:500]],
        }
        coverage = {'windowDays': 28, 'productionReports': int(log_count[0]),
                    'productionDays': int(log_count[1]), 'shiftReports': min(len(reports), 50),
                    'truncated': len(daily) > 200 or len(ingredients) > 500 or len(recipes) > 100 or len(reports) > 50 or len(entries)>200 or len(deductions)>500}
        source = {'snapshotDate':date.today().isoformat(),'focusProductionLogId':log_id,
                  'facts': facts, 'coverage': coverage,
                  'recipes': [{'id': str(r['id']), 'version': r['version'], 'revisionId': str(r['revision_id']),
                               'name': r['name'],'active':r['active'],'yieldAmount':decimal_text(r['yield_amount']),'yieldUnit':r['yield_unit'],
                               'ingredients':[{**i,'productId':str(i['productId'])}
                                              for i in r['ingredients']]} for r in recipes[:100]],
                  'productionEntries':[{'logId':str(r['log_id']),'date':r['business_date'].isoformat(),
                    'sequence':r['sequence'],'recipeId':str(r['recipe_id']),'revisionId':str(r['revision_id']),
                    'name':r['name'],'yieldAmount':decimal_text(r['yield_amount']),'yieldUnit':r['yield_unit'],
                    'batches':r['batches']} for r in entries[:200]],
                  'productionDeductions':[{'logId':str(r['log_id']),'date':r['business_date'].isoformat(),
                    'productId':str(r['product_id']),'name':r['name'],'baseUnit':r['base_unit'],
                    'recipeAmount':decimal_text(r['recipe_amount']),'allowanceAmount':decimal_text(r['allowance_amount']),
                    'quantity':decimal_text(r['quantity']),'allowanceRule':'1%'} for r in deductions[:500]],
                  'stockAsOf':[{'productId':str(r['product_id']),
                    'lastCountedAt':r['last_counted_at'].isoformat() if r['last_counted_at'] else None,
                    'updatedAt':r['updated_at'].isoformat() if r['updated_at'] else None,
                    'version':r['version']} for r in ingredients[:500]],
                  'shiftReports': [{'id': str(r['id']), 'shift': r['shift'], 'notes': r['notes'][:4000],
                                    'createdAt': r['created_at'].isoformat()} for r in reports[:50]]}
        as_of = log_count[2] or date.today()
        return facts, coverage, source, as_of

    def enqueue(self, connection, actor, *, forecast_id, log_id, fingerprint, prompt_version, model, facts, source,
                retry_terminal=False):
        row = connection.execute('''INSERT INTO store_forecasts
            (id,business_id,store_id,log_id,source_fingerprint,prompt_version,model,facts,source_snapshot)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT(store_id,source_fingerprint,prompt_version,model) DO UPDATE SET updated_at=store_forecasts.updated_at
            RETURNING id''', (forecast_id,actor.business_id,actor.store_id,log_id,fingerprint,prompt_version,model,
                              Jsonb(facts),Jsonb(source))).fetchone()
        saved_id = str(row[0])
        connection.execute('''INSERT INTO store_forecast_jobs(forecast_id,business_id,store_id) VALUES(%s,%s,%s)
            ON CONFLICT(forecast_id) DO NOTHING''', (saved_id,actor.business_id,actor.store_id))
        if retry_terminal:
            retried=connection.execute('''UPDATE store_forecast_jobs SET state='queued',attempts=0,available_at=NOW(),
                lease_token=NULL,lease_expires_at=NULL,terminal=false,last_error=NULL,updated_at=NOW()
                WHERE forecast_id=%s AND terminal AND state='failed' RETURNING forecast_id''',(saved_id,)).fetchone()
            if retried:
                connection.execute("UPDATE store_forecasts SET status='queued',error=NULL,generated_at=NULL,updated_at=NOW() WHERE id=%s",(saved_id,))
        return saved_id

    def latest(self, connection, actor, log_id=None):
        found = rows(connection, '''SELECT * FROM store_forecasts WHERE business_id=%s AND store_id=%s
            AND ((%s::uuid IS NULL AND log_id IS NULL) OR log_id=%s::uuid) ORDER BY created_at DESC,id DESC LIMIT 1''',
                     (actor.business_id,actor.store_id,log_id,log_id))
        return found[0] if found else None

    def one(self, connection, actor, forecast_id):
        found = rows(connection, 'SELECT * FROM store_forecasts WHERE business_id=%s AND store_id=%s AND id=%s',
                     (actor.business_id,actor.store_id,forecast_id))
        return found[0] if found else None

    def replay(self, connection, actor, request_id):
        row = connection.execute('''SELECT fingerprint,forecast_id FROM store_forecast_requests
            WHERE business_id=%s AND store_id=%s AND actor_user_id=%s AND request_id=%s''',
            (actor.business_id,actor.store_id,actor.user_id,request_id)).fetchone()
        return row

    def record_request(self, connection, actor, request_id, fingerprint, forecast_id):
        connection.execute('''INSERT INTO store_forecast_requests
            (business_id,store_id,actor_user_id,request_id,fingerprint,forecast_id)
            VALUES(%s,%s,%s,%s,%s,%s)''',
            (actor.business_id,actor.store_id,actor.user_id,request_id,fingerprint,forecast_id))

    def claim(self, connection, lease_seconds=120):
        token = str(uuid4())
        exhausted=connection.execute('''UPDATE store_forecast_jobs SET state='failed',terminal=true,
            lease_token=NULL,lease_expires_at=NULL,last_error='Forecast generation failed.',updated_at=NOW()
            WHERE state='processing' AND lease_expires_at<NOW() AND attempts>=5 RETURNING forecast_id''').fetchall()
        for item in exhausted:
            connection.execute("UPDATE store_forecasts SET status='failed',error='Forecast generation failed.',updated_at=NOW() WHERE id=%s",item)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('''SELECT j.forecast_id FROM store_forecast_jobs j
                WHERE NOT j.terminal AND j.attempts<5 AND j.available_at<=NOW()
                  AND (j.state IN ('queued','failed') OR (j.state='processing' AND j.lease_expires_at<NOW()))
                ORDER BY j.available_at,j.created_at FOR UPDATE SKIP LOCKED LIMIT 1''')
            row = cursor.fetchone()
            if not row: return None
            cursor.execute('''UPDATE store_forecast_jobs SET state='processing',attempts=attempts+1,
                lease_token=%s,lease_expires_at=NOW()+%s*INTERVAL '1 second',updated_at=NOW()
                WHERE forecast_id=%s RETURNING attempts''', (token,lease_seconds,row['forecast_id']))
            attempt = cursor.fetchone()['attempts']
            cursor.execute("UPDATE store_forecasts SET status='processing',error=NULL,updated_at=NOW() WHERE id=%s", (row['forecast_id'],))
            return str(row['forecast_id']),token,attempt

    def job(self, connection, forecast_id):
        found = rows(connection, 'SELECT * FROM store_forecasts WHERE id=%s', (forecast_id,))
        return found[0] if found else None

    def complete(self, connection, forecast_id, token, analysis):
        row = connection.execute('''UPDATE store_forecast_jobs SET state='ready',terminal=true,lease_token=NULL,
            lease_expires_at=NULL,updated_at=NOW() WHERE forecast_id=%s AND state='processing'
            AND lease_token=%s AND lease_expires_at>NOW() RETURNING forecast_id''', (forecast_id,token)).fetchone()
        if not row: return False
        connection.execute('''UPDATE store_forecasts SET status='ready',analysis=%s,error=NULL,
            generated_at=NOW(),updated_at=NOW() WHERE id=%s''', (Jsonb(analysis) if analysis is not None else None,forecast_id))
        return True

    def fail(self, connection, forecast_id, token, attempt, message, retryable=True):
        terminal = not retryable or attempt >= 5
        row = connection.execute('''UPDATE store_forecast_jobs SET state='failed',terminal=%s,last_error=%s,
            available_at=NOW()+(5*power(2,%s))*INTERVAL '1 second',lease_token=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE forecast_id=%s AND state='processing' AND lease_token=%s AND lease_expires_at>NOW() RETURNING forecast_id''',
            (terminal,message,min(attempt-1,5),forecast_id,token)).fetchone()
        if row:
            connection.execute("UPDATE store_forecasts SET status='failed',error=%s,updated_at=NOW() WHERE id=%s", (message,forecast_id))
        return bool(row)
