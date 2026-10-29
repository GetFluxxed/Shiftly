"""Count persistence uses the caller's authorized transaction only."""
import hashlib
import json
from uuid import uuid4

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from ..quantities import decimal_text
from ..packages import PackageRepository
from ..movements import MovementRepository
from ..validation import encode_product_cursor

PAGE_SIZE = 40
MAX_LINES = 10_000


def rows(connection, query, parameters=()):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(query, parameters)
        return cursor.fetchall()


def decimal(value):
    return None if value is None else decimal_text(value)


def timestamp(value):
    return value.isoformat() if value is not None else None


def paged(records, render, *, id_key='product_id'):
    return {'items': [render(row) for row in records[:PAGE_SIZE]],
            'nextCursor': encode_product_cursor(records[PAGE_SIZE-1]['sort_name'], records[PAGE_SIZE-1][id_key]) if len(records)>PAGE_SIZE else None}


def product_snapshot(row):
    return {'productId': str(row['product_id']), 'name': row['name'], 'sku': row['sku'],
            'baseUnit': row['base_unit'], 'containerAmount': decimal(row['container_amount']),
            'packages': row.get('packages', [])}


def observation(row):
    return {**product_snapshot(row), 'id': str(row['id']), 'shelfId': str(row['shelf_id']) if row['shelf_id'] else None,
            'shelfName': row['shelf_name'], 'quantity': decimal(row['quantity']), 'entry': row['entry'],
            'version': row['version'], 'observedAt': timestamp(row['observed_at']), 'observedBy': row['observer_name']}


def comparison(row):
    quantity = row['quantity'] if row['missing'] == 0 else None
    previous = row['previous_quantity']
    return {**product_snapshot(row), 'previousQuantity': decimal(previous), 'quantity': decimal(quantity),
            'difference': decimal(quantity-previous) if quantity is not None and previous is not None else None,
            'locations': row['locations'], 'missing': row['missing']}


def stock_item(row):
    return {**product_snapshot(row), 'quantity': decimal(row['quantity']), 'active': row['active'],
            'countId': str(row['count_id']) if row['count_id'] else None,
            'countedOn': timestamp(row['counted_on']), 'updatedAt': timestamp(row['updated_at']),
            'lastCountedAt': timestamp(row['last_counted_at']), 'lastMovement': row['last_movement_kind'],
            'stockVersion': row['stock_version']}


class CountRepository:
    def scope(self, connection, actor):
        return rows(connection, '''SELECT p.id AS product_id,p.name,p.sku,p.base_unit,p.container_amount,p.version AS product_version,
                   a.shelf_id,s.name AS shelf_name
            FROM inventory_store_products sp JOIN inventory_products p ON p.id=sp.product_id AND p.business_id=sp.business_id
            LEFT JOIN inventory_shelf_products a ON a.store_id=sp.store_id AND a.product_id=p.id AND a.active
            LEFT JOIN inventory_shelves s ON s.id=a.shelf_id AND s.store_id=sp.store_id
            WHERE sp.business_id=%s AND sp.store_id=%s AND sp.active AND p.active
            ORDER BY p.id,a.shelf_id LIMIT %s''', (actor.business_id,actor.store_id,MAX_LINES+1))

    @staticmethod
    def fingerprint(scope):
        frozen = [{key: str(value) if value is not None else None for key,value in row.items()} for row in scope]
        return hashlib.sha256(json.dumps(frozen,sort_keys=True,separators=(',',':')).encode()).hexdigest()

    def count(self, connection, actor, count_id, *, lock=False):
        result = rows(connection, '''SELECT * FROM inventory_counts WHERE business_id=%s AND store_id=%s AND id=%s'''
                      + (' FOR UPDATE' if lock else ''), (actor.business_id,actor.store_id,count_id))
        return result[0] if result else None

    def summary(self, connection, actor, count_id):
        result = rows(connection, '''SELECT c.*,u.username AS starter, reviewer.username AS reviewer, poster.username AS poster,
            (SELECT count(*) FROM inventory_count_lines l WHERE l.count_id=c.id) AS total_lines,
            (SELECT count(*) FROM inventory_count_lines l WHERE l.count_id=c.id AND l.quantity IS NOT NULL) AS counted_lines,
            (SELECT count(*) FROM inventory_count_products p WHERE p.count_id=c.id) AS total_products,
            (SELECT count(*) FROM inventory_count_products p WHERE p.count_id=c.id
              AND NOT EXISTS (SELECT 1 FROM inventory_count_lines l
                WHERE l.count_id=p.count_id AND l.product_id=p.product_id AND l.quantity IS NULL)) AS counted_products
            FROM inventory_counts c JOIN account_users u ON u.id=c.started_by
            LEFT JOIN account_users reviewer ON reviewer.id=c.reviewed_by
            LEFT JOIN account_users poster ON poster.id=c.posted_by
            WHERE c.business_id=%s AND c.store_id=%s AND c.id=%s''', (actor.business_id,actor.store_id,count_id))
        if not result:
            return None
        row = result[0]
        return {'id':str(row['id']), 'storeId':row['store_id'], 'businessDate':timestamp(row['business_date']),
                'state':row['state'], 'version':row['version'], 'startedAt':timestamp(row['started_at']),
                'startedBy':row['starter'], 'reviewedAt':timestamp(row['reviewed_at']), 'reviewedBy':row['reviewer'],
                'postedAt':timestamp(row['posted_at']), 'postedBy':row['poster'],
                'totalLines':row['total_lines'], 'countedLines':row['counted_lines'], 'totalProducts':row['total_products'],
                'countedProducts':row['counted_products']}

    def dashboard(self, connection, actor):
        open_row = connection.execute("SELECT id FROM inventory_counts WHERE store_id=%s AND state IN ('draft','review')", (actor.store_id,)).fetchone()
        last_row = connection.execute("SELECT id FROM inventory_counts WHERE store_id=%s AND state='posted' ORDER BY posted_at DESC,id DESC LIMIT 1", (actor.store_id,)).fetchone()
        return {'storeId':actor.store_id,
                'openCount':self.summary(connection,actor,open_row[0]) if open_row else None,
                'lastCount':self.summary(connection,actor,last_row[0]) if last_row else None}

    def create(self, connection, actor, count_id, business_date, scope):
        connection.execute('''INSERT INTO inventory_counts(id,business_id,store_id,business_date,configuration_hash,started_by)
            VALUES(%s,%s,%s,%s,%s,%s)''', (count_id,actor.business_id,actor.store_id,business_date,self.fingerprint(scope),actor.user_id))
        products = {row['product_id']:row for row in scope}
        for product in products.values():
            connection.execute('''INSERT INTO inventory_count_products(business_id,store_id,count_id,product_id,name,sku,base_unit,
                  container_amount,product_version,packages,previous_quantity,previous_count_id,previous_stock_version)
                SELECT %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,b.quantity,b.count_id,b.version
                FROM (SELECT 1) seed LEFT JOIN inventory_stock_balances b
                  ON b.business_id=%s AND b.store_id=%s AND b.product_id=%s''',
                (actor.business_id,actor.store_id,count_id,product['product_id'],product['name'],product['sku'],product['base_unit'],
                 product['container_amount'],product['product_version'],
                 Jsonb(PackageRepository().packages(connection, actor.business_id, product['product_id'], active_only=True)),
                 actor.business_id,actor.store_id,product['product_id']))
        with connection.cursor() as cursor:
            cursor.executemany('''INSERT INTO inventory_count_lines(id,business_id,store_id,count_id,product_id,shelf_id,shelf_name)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                [(str(uuid4()),actor.business_id,actor.store_id,count_id,row['product_id'],row['shelf_id'],row['shelf_name'] or 'Unassigned') for row in scope])

    def line(self, connection, actor, count_id, line_id):
        result = rows(connection, '''SELECT l.*,p.name,p.sku,p.base_unit,p.container_amount,p.packages,u.username AS observer_name
            FROM inventory_count_lines l JOIN inventory_count_products p ON p.count_id=l.count_id AND p.product_id=l.product_id
            LEFT JOIN account_users u ON u.id=l.observed_by
            WHERE l.business_id=%s AND l.store_id=%s AND l.count_id=%s AND l.id=%s''', (actor.business_id,actor.store_id,count_id,line_id))
        return result[0] if result else None

    def save_line(self, connection, actor, count_id, line_id, quantity, entry):
        connection.execute('''UPDATE inventory_count_lines SET quantity=%s,entry=%s,version=version+1,observed_by=%s,observed_at=NOW()
            WHERE count_id=%s AND id=%s AND store_id=%s''', (quantity,Jsonb(entry),actor.user_id,count_id,line_id,actor.store_id))
        connection.execute('UPDATE inventory_counts SET version=version+1,updated_at=NOW() WHERE id=%s', (count_id,))

    def lines(self, connection, actor, count_id, query, after, shelf, missing):
        name, identifier = after or (None,None)
        result = rows(connection, '''SELECT l.*,p.name,p.sku,p.base_unit,p.container_amount,p.packages,u.username AS observer_name,
                   (inventory_key(p.name)||' / '||inventory_key(l.shelf_name)) COLLATE "C" AS sort_name
            FROM inventory_count_lines l JOIN inventory_count_products p ON p.count_id=l.count_id AND p.product_id=l.product_id
            LEFT JOIN account_users u ON u.id=l.observed_by
            WHERE l.business_id=%s AND l.store_id=%s AND l.count_id=%s
              AND (strpos(lower(p.name),lower(%s))>0 OR strpos(lower(p.sku),lower(%s))>0)
              AND (%s='' OR (%s='unassigned' AND l.shelf_id IS NULL) OR l.shelf_id::text=%s)
              AND (NOT %s OR l.quantity IS NULL)
              AND (%s::text IS NULL OR ((inventory_key(p.name)||' / '||inventory_key(l.shelf_name)) COLLATE "C",l.id)>(%s::text COLLATE "C",%s::uuid))
            ORDER BY sort_name,l.id LIMIT %s''',
            (actor.business_id,actor.store_id,count_id,query,query,shelf,shelf,shelf,missing,name,name,identifier,PAGE_SIZE+1))
        return paged(result,observation,id_key='id')

    def comparisons(self, connection, actor, count_id, query='', after=None):
        name, identifier = after or (None,None)
        result = rows(connection, '''SELECT p.*,inventory_key(p.name) COLLATE "C" AS sort_name,
                   sum(l.quantity) AS quantity,count(*) AS locations,count(*) FILTER (WHERE l.quantity IS NULL) AS missing
            FROM inventory_count_products p JOIN inventory_count_lines l ON l.count_id=p.count_id AND l.product_id=p.product_id
            WHERE p.business_id=%s AND p.store_id=%s AND p.count_id=%s
              AND (strpos(lower(p.name),lower(%s))>0 OR strpos(lower(p.sku),lower(%s))>0)
              AND (%s::text IS NULL OR (inventory_key(p.name) COLLATE "C",p.product_id)>(%s::text COLLATE "C",%s::uuid))
            GROUP BY p.count_id,p.product_id ORDER BY sort_name,p.product_id LIMIT %s''',
            (actor.business_id,actor.store_id,count_id,query,query,name,name,identifier,PAGE_SIZE+1))
        return paged(result,comparison)

    def totals(self, connection, actor, count_id):
        return rows(connection, '''SELECT p.product_id,p.base_unit,p.previous_quantity,p.previous_count_id,p.previous_stock_version,
                   sum(l.quantity) AS quantity,count(*) FILTER(WHERE l.quantity IS NULL) AS missing,
                   b.quantity AS current_quantity,b.count_id AS current_count_id,b.version AS current_stock_version
            FROM inventory_count_products p JOIN inventory_count_lines l ON l.count_id=p.count_id AND l.product_id=p.product_id
            LEFT JOIN inventory_stock_balances b ON b.store_id=p.store_id AND b.product_id=p.product_id
            WHERE p.business_id=%s AND p.store_id=%s AND p.count_id=%s
            GROUP BY p.count_id,p.product_id,b.quantity,b.count_id,b.version''', (actor.business_id,actor.store_id,count_id))

    def transition(self, connection, actor, count_id, state):
        if state == 'review':
            connection.execute("UPDATE inventory_counts SET state='review',version=version+1,updated_at=NOW(),reviewed_by=%s,reviewed_at=NOW() WHERE id=%s", (actor.user_id,count_id))
        elif state == 'posted':
            connection.execute("UPDATE inventory_counts SET state='posted',version=version+1,updated_at=NOW(),posted_by=%s,posted_at=NOW() WHERE id=%s", (actor.user_id,count_id))
        else:
            connection.execute('UPDATE inventory_counts SET state=%s,version=version+1,updated_at=NOW() WHERE id=%s', (state,count_id))

    def post(self, connection, actor, count, totals):
        for row in totals:
            connection.execute('''INSERT INTO inventory_stock_postings(business_id,store_id,count_id,product_id,quantity_before,quantity_after,posted_by)
                VALUES(%s,%s,%s,%s,%s,%s,%s)''', (actor.business_id,actor.store_id,count['id'],row['product_id'],row['previous_quantity'],row['quantity'],actor.user_id))
            MovementRepository().apply(connection,actor,product_id=row['product_id'],base_unit=row['base_unit'],
                quantity_after=row['quantity'],kind='count',source_id=count['id'],count_id=count['id'],counted_on=count['business_date'])
        self.transition(connection,actor,count['id'],'posted')

    def history(self, connection, actor, after):
        result = rows(connection, '''SELECT id FROM inventory_counts WHERE business_id=%s AND store_id=%s AND state IN ('posted','cancelled')
            AND (%s::uuid IS NULL OR (started_at,id)<(SELECT started_at,id FROM inventory_counts WHERE id=%s AND store_id=%s))
            ORDER BY started_at DESC,id DESC LIMIT %s''', (actor.business_id,actor.store_id,after,after,actor.store_id,PAGE_SIZE+1))
        return {'items':[self.summary(connection,actor,row['id']) for row in result[:PAGE_SIZE]],
                'nextCursor':str(result[PAGE_SIZE-1]['id']) if len(result)>PAGE_SIZE else None}

    def stock(self, connection, actor, query='', after=None, shelf='', product_id=None):
        name, identifier = after or (None,None)
        result = rows(connection, '''SELECT p.id AS product_id,p.name,p.sku,COALESCE(b.base_unit,p.base_unit) AS base_unit,p.container_amount,
                   sp.active AND p.active AS active,b.quantity,b.count_id,b.counted_on,b.updated_at,p.name_sort AS sort_name,
                   b.last_counted_at,b.version AS stock_version,m.kind AS last_movement_kind
            FROM inventory_store_products sp JOIN inventory_products p ON p.business_id=sp.business_id AND p.id=sp.product_id
            LEFT JOIN inventory_stock_balances b ON b.business_id=sp.business_id AND b.store_id=sp.store_id AND b.product_id=sp.product_id
            LEFT JOIN inventory_stock_movements m ON m.id=b.last_movement_id
            WHERE sp.business_id=%s AND sp.store_id=%s AND ((sp.active AND p.active) OR b.product_id IS NOT NULL)
              AND (%s::uuid IS NULL OR p.id=%s)
              AND (strpos(lower(p.name),lower(%s))>0 OR strpos(lower(p.sku),lower(%s))>0)
              AND (%s='' OR EXISTS(SELECT 1 FROM inventory_shelf_products a WHERE a.store_id=sp.store_id AND a.product_id=p.id AND a.active AND a.shelf_id::text=%s)
                  OR (%s='unassigned' AND NOT EXISTS(SELECT 1 FROM inventory_shelf_products a WHERE a.store_id=sp.store_id AND a.product_id=p.id AND a.active)))
              AND (%s::text IS NULL OR (p.name_sort,p.id)>(%s::text COLLATE "C",%s::uuid))
            ORDER BY p.name_sort,p.id LIMIT %s''',
            (actor.business_id,actor.store_id,product_id,product_id,query,query,shelf,shelf,shelf,name,name,identifier,PAGE_SIZE+1))
        return paged(result,stock_item)

    def stock_locations(self, connection, actor, product_id, count_id, after):
        result = rows(connection, '''SELECT l.*,p.name,p.sku,p.base_unit,p.container_amount,p.packages,u.username AS observer_name
            FROM inventory_count_lines l JOIN inventory_count_products p ON p.count_id=l.count_id AND p.product_id=l.product_id
            LEFT JOIN account_users u ON u.id=l.observed_by
            WHERE l.business_id=%s AND l.store_id=%s AND l.product_id=%s AND l.count_id=%s AND (%s::uuid IS NULL OR l.id>%s)
            ORDER BY l.id LIMIT %s''', (actor.business_id,actor.store_id,product_id,count_id,after,after,PAGE_SIZE+1))
        return {'items':[observation(row) for row in result[:PAGE_SIZE]], 'nextCursor':str(result[PAGE_SIZE-1]['id']) if len(result)>PAGE_SIZE else None}
