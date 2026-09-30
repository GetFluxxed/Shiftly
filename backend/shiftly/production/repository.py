from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from backend.shiftly.inventory.quantities import decimal_text
from backend.shiftly.inventory.validation import encode_product_cursor

PAGE_SIZE=40


def rows(connection,query,parameters=()):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query,parameters); return cursor.fetchall()


def timestamp(value): return value.isoformat() if value is not None else None
def decimal(value): return decimal_text(value) if value is not None else None


class ProductionRepository:
    def products(self,connection,actor,product_ids):
        if not product_ids:return {}
        found=rows(connection,'''SELECT p.id,p.name,p.sku,p.base_unit FROM inventory_products p
          WHERE p.business_id=%s AND p.id=ANY(%s::uuid[]) AND p.active''',(actor.business_id,list(product_ids)))
        return {str(row['id']):row for row in found}

    def active_products(self,connection,actor,product_ids):
        if not product_ids:return set()
        found=rows(connection,'''SELECT p.id FROM inventory_products p JOIN inventory_store_products sp
          ON sp.business_id=p.business_id AND sp.product_id=p.id
          WHERE p.business_id=%s AND sp.store_id=%s AND p.id=ANY(%s::uuid[]) AND p.active AND sp.active''',
          (actor.business_id,actor.store_id,list(product_ids)))
        return {str(row['id']) for row in found}

    def recipe(self,connection,actor,recipe_id,revision_id=None,*,lock=False,current_only=False):
        result=rows(connection,'''SELECT r.id,r.version,r.current_revision_id,v.id revision_id,v.name,v.yield_amount,v.yield_unit,v.instructions
          FROM production_recipes r JOIN production_recipe_revisions v ON v.recipe_id=r.id
          WHERE r.business_id=%s AND r.id=%s AND v.id=COALESCE(%s::uuid,r.current_revision_id)
            AND (NOT %s OR v.id=r.current_revision_id)'''+(' FOR UPDATE OF r' if lock else ''),
          (actor.business_id,recipe_id,revision_id,current_only))
        return self.render_recipe(connection,result[0]) if result else None

    def render_recipe(self,connection,row):
        ingredients=rows(connection,'''SELECT product_id,name,sku,amount,unit,base_unit,base_amount FROM production_recipe_ingredients
          WHERE revision_id=%s ORDER BY inventory_key(name) COLLATE "C",product_id''',(row['revision_id'],))
        return {'id':str(row['id']),'name':row['name'],'version':row['version'],'revisionId':str(row['revision_id']),
          'yieldAmount':decimal(row['yield_amount']),'yieldUnit':row['yield_unit'],'instructions':row['instructions'],
          'ingredients':[{'productId':str(i['product_id']),'name':i['name'],'sku':i['sku'],'amount':decimal(i['amount']),
                          'unit':i['unit'],'baseUnit':i['base_unit'],'baseAmount':decimal(i['base_amount'])} for i in ingredients]}

    def recipes(self,connection,actor,query,after):
        name,identifier=after or (None,None)
        found=rows(connection,'''SELECT r.id,r.version,r.current_revision_id,v.id revision_id,v.name,v.yield_amount,v.yield_unit,v.instructions,
          inventory_key(v.name) COLLATE "C" AS sort_name
          FROM production_recipes r JOIN production_recipe_revisions v ON v.id=r.current_revision_id
          WHERE r.business_id=%s AND strpos(lower(v.name),lower(%s))>0
            AND (%s::text IS NULL OR (inventory_key(v.name) COLLATE "C",r.id)>(%s::text COLLATE "C",%s::uuid))
          ORDER BY sort_name,r.id LIMIT %s''',(actor.business_id,query,name,name,identifier,PAGE_SIZE+1))
        return {'items':[self.render_recipe(connection,r) for r in found[:PAGE_SIZE]],
                'nextCursor':encode_product_cursor(found[PAGE_SIZE-1]['sort_name'],found[PAGE_SIZE-1]['id']) if len(found)>PAGE_SIZE else None}

    def create_recipe(self,connection,actor,recipe_id,revision_id,data,products):
        connection.execute('INSERT INTO production_recipes(id,business_id,current_revision_id,created_by) VALUES(%s,%s,NULL,%s)',(recipe_id,actor.business_id,actor.user_id))
        self._revision(connection,actor,recipe_id,revision_id,1,data,products)
        connection.execute('UPDATE production_recipes SET current_revision_id=%s WHERE id=%s',(revision_id,recipe_id))

    def revise_recipe(self,connection,actor,recipe_id,revision_id,version,data,products):
        self._revision(connection,actor,recipe_id,revision_id,version+1,data,products)
        connection.execute('UPDATE production_recipes SET current_revision_id=%s,version=version+1,updated_at=NOW() WHERE id=%s',(revision_id,recipe_id))

    def _revision(self,connection,actor,recipe_id,revision_id,number,data,products):
        connection.execute('''INSERT INTO production_recipe_revisions(id,business_id,recipe_id,revision_number,name,yield_amount,yield_unit,instructions,created_by)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(revision_id,actor.business_id,recipe_id,number,data['name'],data['yieldAmount'],data['yieldUnit'],data['instructions'],actor.user_id))
        for item in data['ingredients']:
            p=products[item['productId']]
            connection.execute('''INSERT INTO production_recipe_ingredients(business_id,recipe_id,revision_id,product_id,name,sku,amount,unit,base_unit,base_amount)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(actor.business_id,recipe_id,revision_id,item['productId'],p['name'],p['sku'],item['amount'],item['unit'],p['base_unit'],item['baseAmount']))
        connection.execute('UPDATE production_recipe_revisions SET sealed=true WHERE id=%s',(revision_id,))

    def request(self,connection,actor,request_id):
        found=rows(connection,'SELECT fingerprint,result FROM production_requests WHERE business_id=%s AND store_id=%s AND request_id=%s',(actor.business_id,actor.store_id,request_id))
        return found[0] if found else None

    def record_request(self,connection,actor,request_id,fingerprint,result):
        connection.execute('INSERT INTO production_requests(business_id,store_id,request_id,fingerprint,result) VALUES(%s,%s,%s,%s,%s)',(actor.business_id,actor.store_id,request_id,fingerprint,Jsonb(result)))

    def log_by_id(self,connection,actor,log_id,*,lock=False):
        found=rows(connection,'SELECT * FROM production_logs WHERE business_id=%s AND store_id=%s AND id=%s'+(' FOR UPDATE' if lock else ''),(actor.business_id,actor.store_id,log_id))
        return found[0] if found else None

    def log(self,connection,actor,log_id):
        header=self.log_by_id(connection,actor,log_id)
        if not header:return None
        entries=rows(connection,'SELECT * FROM production_log_entries WHERE log_id=%s ORDER BY sequence',(log_id,))
        ingredients=rows(connection,'SELECT * FROM production_log_ingredients WHERE log_id=%s ORDER BY name,product_id',(log_id,))
        return {'id':str(header['id']),'businessDate':header['business_date'].isoformat(),'state':header['state'],
          'createdAt':timestamp(header['created_at']),'createdBy':header['creator_name'],
          'entries':[{'recipeId':str(e['recipe_id']),'revisionId':str(e['revision_id']),'name':e['name'],'yieldAmount':decimal(e['yield_amount']),'yieldUnit':e['yield_unit'],'batches':e['batches']} for e in entries],
          'ingredients':[{'productId':str(i['product_id']),'name':i['name'],'sku':i['sku'],'baseUnit':i['base_unit'],
            'recipeAmount':decimal(i['recipe_amount']),'allowanceAmount':decimal(i['allowance_amount']),'quantity':decimal(i['quantity']),
            'balance':decimal(i['balance_before']),'remaining':decimal(i['balance_after'])} for i in ingredients],
          **({'reversalReason':header['reversal_reason']} if header['reversal_reason'] else {})}

    def logs(self,connection,actor,after):
        found=rows(connection,'''SELECT id FROM production_logs WHERE business_id=%s AND store_id=%s
          AND (%s::uuid IS NULL OR (created_at,id)<(SELECT created_at,id FROM production_logs WHERE id=%s AND store_id=%s))
          ORDER BY created_at DESC,id DESC LIMIT %s''',(actor.business_id,actor.store_id,after,after,actor.store_id,PAGE_SIZE+1))
        return {'items':[self.log(connection,actor,r['id']) for r in found[:PAGE_SIZE]],'nextCursor':str(found[PAGE_SIZE-1]['id']) if len(found)>PAGE_SIZE else None}

    def create_log(self,connection,actor,log_id,business_date,payload_fingerprint,entries,ingredients):
        connection.execute('''INSERT INTO production_logs(id,business_id,store_id,business_date,state,payload_fingerprint,created_by,creator_name)
          VALUES(%s,%s,%s,%s,'building',%s,%s,%s)''',(log_id,actor.business_id,actor.store_id,business_date,payload_fingerprint,actor.user_id,actor.display_name))
        for n,e in enumerate(entries):
            connection.execute('''INSERT INTO production_log_entries(business_id,store_id,log_id,sequence,recipe_id,revision_id,name,yield_amount,yield_unit,batches)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(actor.business_id,actor.store_id,log_id,n,e['recipeId'],e['revisionId'],e['name'],e['yieldAmount'],e['yieldUnit'],e['batches']))
        for i in ingredients:
            connection.execute('''INSERT INTO production_log_ingredients(business_id,store_id,log_id,product_id,name,sku,base_unit,recipe_amount,allowance_amount,quantity,balance_before,balance_after,count_id,movement_id)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',(actor.business_id,actor.store_id,log_id,i['productId'],i['name'],i['sku'],i['baseUnit'],i['recipeAmount'],i['allowanceAmount'],i['quantity'],i['balance'],i['remaining'],i['countId'],i['movementId']))
        connection.execute("UPDATE production_logs SET state='confirmed' WHERE id=%s",(log_id,))

    def reversal_rows(self,connection,log_id):
        return rows(connection,'SELECT * FROM production_log_ingredients WHERE log_id=%s ORDER BY product_id',(log_id,))

    def reverse(self,connection,actor,log_id,reason):
        connection.execute("UPDATE production_logs SET state='reversed',reversal_reason=%s,reversed_by=%s,reversed_at=NOW() WHERE id=%s",(reason,actor.user_id,log_id))
