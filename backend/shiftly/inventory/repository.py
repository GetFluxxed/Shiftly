"""Inventory SQL uses the service's transaction; no identity or runtime internals."""
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from .quantities import decimal_text
from .validation import encode_product_cursor

PAGE_SIZE = 40


def product(row):
    return {'id': str(row['id']), 'name': row['name'], 'sku': row['sku'],
            'baseUnit': row['base_unit'], 'active': row['active'], 'version': row['version'],
            'containerAmount': decimal_text(row['container_amount']) if row['container_amount'] is not None else None}


def shelf(row):
    return {'id': str(row['id']), 'name': row['name'], 'version': row['version'], 'storeId': row['store_id']}


class InventoryRepository:
    def product(self, connection, business_id, product_id):
        with connection.cursor(row_factory=dict_row) as c:
            c.execute('SELECT * FROM inventory_products WHERE business_id=%s AND id=%s', (business_id, product_id))
            row = c.fetchone()
            return product(row) if row else None

    def products(self, connection, business_id, query, after, state):
        after_name, after_id = after if after else (None, None)
        with connection.cursor(row_factory=dict_row) as c:
            c.execute('''SELECT p.* FROM inventory_products p WHERE business_id=%s
                         AND (%s='all' OR p.active=(%s='active'))
                         AND (%s::text IS NULL OR (p.name_sort,p.id)>(%s::text COLLATE "C",%s::uuid))
                         AND (strpos(lower(p.name),lower(%s))>0 OR EXISTS (
                             SELECT 1 FROM inventory_product_skus s WHERE s.business_id=p.business_id
                             AND s.product_id=p.id AND strpos(s.sku_key,inventory_key(%s))>0))
                         ORDER BY p.name_sort,p.id LIMIT %s''', (business_id, state, state, after_name, after_name, after_id, query, query, PAGE_SIZE+1))
            rows = c.fetchall()
        return {'items': [product(r) for r in rows[:PAGE_SIZE]],
                'nextCursor': encode_product_cursor(rows[PAGE_SIZE-1]['name_sort'], rows[PAGE_SIZE-1]['id']) if len(rows)>PAGE_SIZE else None}

    def reserve_sku(self, connection, business_id, product_id, sku):
        row = connection.execute('SELECT product_id FROM inventory_product_skus WHERE business_id=%s AND sku_key=inventory_key(%s)',
                                 (business_id, sku)).fetchone()
        if row:
            return str(row[0]) == product_id
        connection.execute('INSERT INTO inventory_product_skus(business_id,product_id,sku) VALUES(%s,%s,%s)',
                           (business_id, product_id, sku))
        return True

    def create_product(self, connection, actor, product_id, fields):
        connection.execute('INSERT INTO inventory_products(id,business_id,sku,name,base_unit,container_amount) VALUES(%s,%s,%s,%s,%s,%s)',
                           (product_id, actor.business_id, fields['sku'], fields['name'], fields['baseUnit'], fields.get('containerAmount')))

    def edit_product(self, connection, actor, product_id, fields):
        connection.execute('UPDATE inventory_products SET name=%s,sku=%s,container_amount=%s,version=version+1,updated_at=NOW() WHERE business_id=%s AND id=%s',
                           (fields['name'], fields['sku'], fields['containerAmount'], actor.business_id, product_id))

    def product_state(self, connection, actor, product_id, active):
        connection.execute('UPDATE inventory_products SET active=%s,version=version+1,updated_at=NOW() WHERE business_id=%s AND id=%s',
                           (active, actor.business_id, product_id))

    def shelves(self, connection, store_id, after):
        with connection.cursor(row_factory=dict_row) as c:
            c.execute('SELECT * FROM inventory_shelves WHERE store_id=%s AND (%s::uuid IS NULL OR id>%s::uuid) ORDER BY id LIMIT %s',
                      (store_id, after, after, PAGE_SIZE+1))
            rows = c.fetchall()
        return {'items': [shelf(r) for r in rows[:PAGE_SIZE]],
                'nextCursor': str(rows[PAGE_SIZE-1]['id']) if len(rows)>PAGE_SIZE else None}

    def shelf(self, connection, store_id, shelf_id):
        with connection.cursor(row_factory=dict_row) as c:
            c.execute('SELECT * FROM inventory_shelves WHERE store_id=%s AND id=%s', (store_id, shelf_id))
            row = c.fetchone()
            return shelf(row) if row else None

    def placements(self, connection, store_id, shelf_id, after):
        with connection.cursor(row_factory=dict_row) as c:
            c.execute('''SELECT p.* FROM inventory_shelf_products a JOIN inventory_products p
                         ON p.business_id=a.business_id AND p.id=a.product_id
                         WHERE a.store_id=%s AND a.shelf_id=%s AND a.active
                           AND (%s::uuid IS NULL OR p.id>%s::uuid) ORDER BY p.id LIMIT %s''',
                      (store_id, shelf_id, after, after, PAGE_SIZE+1))
            rows = c.fetchall()
        return {'items': [product(r) for r in rows[:PAGE_SIZE]],
                'nextCursor': str(rows[PAGE_SIZE-1]['id']) if len(rows)>PAGE_SIZE else None}

    def create_shelf(self, connection, actor, shelf_id, name):
        connection.execute('INSERT INTO inventory_shelves(id,business_id,store_id,name) VALUES(%s,%s,%s,%s)',
                           (shelf_id, actor.business_id, actor.store_id, name))

    def edit_shelf(self, connection, actor, shelf_id, name):
        connection.execute('UPDATE inventory_shelves SET name=%s,version=version+1,updated_at=NOW() WHERE store_id=%s AND id=%s',
                           (name, actor.store_id, shelf_id))

    def placement(self, connection, actor, shelf_id, product_id, active):
        existing = connection.execute('SELECT active FROM inventory_shelf_products WHERE store_id=%s AND shelf_id=%s AND product_id=%s',
                                      (actor.store_id, shelf_id, product_id)).fetchone()
        before = bool(existing and existing[0])
        if before == active:
            return before
        if active:
            connection.execute('''INSERT INTO inventory_store_products(business_id,store_id,product_id) VALUES(%s,%s,%s)
                               ON CONFLICT (business_id,store_id,product_id) DO UPDATE SET active=true''',
                               (actor.business_id, actor.store_id, product_id))
        connection.execute('''INSERT INTO inventory_shelf_products(business_id,store_id,shelf_id,product_id,active) VALUES(%s,%s,%s,%s,%s)
                           ON CONFLICT(store_id,shelf_id,product_id) DO UPDATE SET active=EXCLUDED.active,updated_at=NOW()''',
                           (actor.business_id, actor.store_id, shelf_id, product_id, active))
        connection.execute('UPDATE inventory_shelves SET version=version+1,updated_at=NOW() WHERE store_id=%s AND id=%s', (actor.store_id, shelf_id))
        return before

    def replay(self, connection, actor, request_id):
        return connection.execute('SELECT fingerprint,result FROM inventory_requests WHERE business_id=%s AND store_id=%s AND actor_user_id=%s AND request_id=%s',
                                  (actor.business_id, actor.store_id, actor.user_id, request_id)).fetchone()

    def record(self, connection, actor, request_id, fingerprint, operation, target, before, after, result):
        connection.execute('''INSERT INTO inventory_changes(business_id,store_id,actor_user_id,operation,target_id,before_value,after_value)
                           VALUES(%s,%s,%s,%s,%s,%s,%s)''',
                           (actor.business_id, actor.store_id, actor.user_id, operation, target, Jsonb(before), Jsonb(after)))
        connection.execute('INSERT INTO inventory_requests(business_id,store_id,actor_user_id,request_id,fingerprint,result) VALUES(%s,%s,%s,%s,%s,%s)',
                           (actor.business_id, actor.store_id, actor.user_id, request_id, fingerprint, Jsonb(result)))
