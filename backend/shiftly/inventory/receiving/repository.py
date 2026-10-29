"""SQL persistence for store-scoped invoice drafts; never writes stock."""
from decimal import Decimal
from psycopg.rows import dict_row

from ..quantities import decimal_text
from .validation import encode_cursor, encode_product_cursor

PAGE_SIZE = 40
MAX_STOCK = Decimal('999999999999999.999999999')


def summary(row):
    return {'id': str(row['id']), 'supplier': row['supplier'], 'invoiceNumber': row['invoice_number'],
            'state': row['state'], 'version': row['version'], 'lineCount': row['line_count'],
            'receivedCount': row['received_count'], 'updatedAt': row['updated_at'].isoformat()}


def line_output(row):
    return {'id': str(row['id']), 'description': row['description'], 'sku': row['sku'],
            'productId': str(row['product_id']) if row['product_id'] else None,
            'packageId': str(row['package_id']) if row['package_id'] else None,
            'quantity': decimal_text(row['quantity']) if row['quantity'] is not None else None,
            'unit': row['unit'], 'received': row['received'], 'productName': row['product_name'],
            'baseUnit': row['base_unit'],
            'normalizedQuantity': decimal_text(row['normalized_quantity']) if row['normalized_quantity'] is not None else None,
            'packageName': row['package_name'], 'needsCatalogReview': bool(row.get('needs_catalog_review', False))}


class ReceivingRepository:
    def summaries(self, connection, actor, query, after, *, photo_reading_available=False):
        timestamp, item_id = after if after else (None, None)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('''SELECT d.*,count(l.id)::int AS line_count,
                              count(l.id) FILTER (WHERE l.received)::int AS received_count
                FROM inventory_invoice_drafts d LEFT JOIN inventory_invoice_lines l ON l.invoice_id=d.id
                WHERE d.business_id=%s AND d.store_id=%s
                  AND (%s='' OR strpos(lower(d.supplier),lower(%s))>0 OR strpos(lower(d.invoice_number),lower(%s))>0)
                  AND (%s::timestamptz IS NULL OR (d.updated_at,d.id)<(%s::timestamptz,%s::uuid))
                GROUP BY d.id ORDER BY d.updated_at DESC,d.id DESC LIMIT %s''',
                (actor.business_id, actor.store_id, query, query, query, timestamp, timestamp, item_id, PAGE_SIZE + 1))
            rows = cursor.fetchall()
        return {'items': [summary(row) for row in rows[:PAGE_SIZE]],
                'nextCursor': encode_cursor(rows[PAGE_SIZE-1]['updated_at'], rows[PAGE_SIZE-1]['id']) if len(rows)>PAGE_SIZE else None,
                'photoReadingAvailable': photo_reading_available}

    def baseline(self, connection, actor):
        row = connection.execute("SELECT id FROM inventory_counts WHERE business_id=%s AND store_id=%s AND state='posted' ORDER BY posted_at DESC,id DESC LIMIT 1",
                                 (actor.business_id, actor.store_id)).fetchone()
        return str(row[0]) if row else None

    def is_stale(self, connection, actor, baseline_count_id):
        if baseline_count_id:
            return connection.execute('''SELECT EXISTS(SELECT 1 FROM inventory_counts newer
                JOIN inventory_counts baseline ON baseline.id=%s
                WHERE newer.business_id=%s AND newer.store_id=%s AND newer.state='posted'
                  AND (newer.posted_at,newer.id)>(baseline.posted_at,baseline.id))''',
                (baseline_count_id, actor.business_id, actor.store_id)).fetchone()[0]
        return connection.execute("SELECT EXISTS(SELECT 1 FROM inventory_counts WHERE business_id=%s AND store_id=%s AND state='posted')",
                                  (actor.business_id, actor.store_id)).fetchone()[0]

    def catalog_review(self, connection, actor, invoice_id):
        return connection.execute('''SELECT EXISTS(SELECT 1 FROM inventory_invoice_lines l
            LEFT JOIN inventory_products p ON p.business_id=l.business_id AND p.id=l.product_id
            LEFT JOIN inventory_packages k ON k.business_id=l.business_id AND k.id=l.package_id
            WHERE l.invoice_id=%s AND l.product_id IS NOT NULL AND (
              p.id IS NULL OR NOT p.active OR p.canonical_product_id IS NOT NULL OR p.base_unit<>l.base_unit OR
              (l.package_id IS NOT NULL AND (k.id IS NULL OR NOT k.active OR k.product_id<>l.product_id OR k.amount<>l.package_amount))))''',
            (invoice_id,)).fetchone()[0]

    def create(self, connection, actor, invoice_id, fields, baseline):
        connection.execute('''INSERT INTO inventory_invoice_drafts
            (id,business_id,store_id,supplier,invoice_number,baseline_count_id,created_by)
            VALUES(%s,%s,%s,%s,%s,%s,%s)''',
            (invoice_id, actor.business_id, actor.store_id, fields['supplier'], fields['invoiceNumber'], baseline, actor.user_id))

    def header(self, connection, actor, invoice_id, *, lock=False):
        suffix = ' FOR UPDATE' if lock else ''
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM inventory_invoice_drafts WHERE business_id=%s AND store_id=%s AND id=%s' + suffix,
                           (actor.business_id, actor.store_id, invoice_id))
            return cursor.fetchone()

    def draft(self, connection, actor, invoice_id, *, lock=False):
        row = self.header(connection, actor, invoice_id, lock=lock)
        if not row:
            return None
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('''SELECT l.*,CASE WHEN l.product_id IS NULL THEN false ELSE
                p.id IS NULL OR NOT p.active OR p.canonical_product_id IS NOT NULL OR p.base_unit<>l.base_unit OR
                (l.package_id IS NOT NULL AND (k.id IS NULL OR NOT k.active OR k.product_id<>l.product_id OR k.amount<>l.package_amount))
                END AS needs_catalog_review
                FROM inventory_invoice_lines l
                LEFT JOIN inventory_products p ON p.business_id=l.business_id AND p.id=l.product_id
                LEFT JOIN inventory_packages k ON k.business_id=l.business_id AND k.id=l.package_id
                WHERE l.invoice_id=%s ORDER BY l.position,l.id''', (invoice_id,))
            lines = cursor.fetchall()
            cursor.execute('''SELECT count(*)::int AS line_count,
                              count(*) FILTER (WHERE received)::int AS received_count
                              FROM inventory_invoice_lines WHERE invoice_id=%s''', (invoice_id,))
            counts = cursor.fetchone()
        result = {**summary({**row, **counts}), 'storeId': row['store_id'],
                  'lines': [line_output(item) for item in lines],
                  'needsCountReview': self.is_stale(connection, actor, row['baseline_count_id']),
                  'needsCatalogReview': self.catalog_review(connection, actor, invoice_id),
                  'createdAt': row['created_at'].isoformat(),
                  'baselineCountId': str(row['baseline_count_id']) if row['baseline_count_id'] else None}
        return result

    def lines_raw(self, connection, invoice_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM inventory_invoice_lines WHERE invoice_id=%s ORDER BY position,id', (invoice_id,))
            return {str(row['id']): row for row in cursor.fetchall()}

    def catalog(self, connection, actor, product_id, package_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('''SELECT canonical.id,canonical.name,canonical.base_unit,canonical.version,canonical.active
                FROM inventory_products source
                JOIN inventory_products canonical ON canonical.business_id=source.business_id
                  AND canonical.id=COALESCE(source.canonical_product_id,source.id)
                WHERE source.business_id=%s AND source.id=%s
                FOR SHARE OF source,canonical''', (actor.business_id, product_id))
            product = cursor.fetchone()
            if not product:
                return None
            package = None
            if package_id:
                cursor.execute('''SELECT target.id AS package_id,target.name AS package_name,target.amount AS package_amount,
                                         target.version AS package_version,target.active AS package_active
                    FROM inventory_packages supplied
                    JOIN inventory_packages target ON target.business_id=supplied.business_id
                      AND target.id=COALESCE(supplied.redirect_package_id,supplied.id)
                    WHERE supplied.business_id=%s AND supplied.product_id=%s AND supplied.id=%s
                      AND target.product_id=%s FOR SHARE OF supplied,target''',
                    (actor.business_id, product_id, package_id, product['id']))
                package = cursor.fetchone()
            return {**product, **(package or {'package_id': None, 'package_name': None, 'package_amount': None,
                                               'package_version': None, 'package_active': None})}

    def replace(self, connection, actor, invoice_id, fields, snapshots, *, bump=True):
        connection.execute('DELETE FROM inventory_invoice_lines WHERE invoice_id=%s', (invoice_id,))
        for position, (item, snap) in enumerate(zip(fields['lines'], snapshots)):
            connection.execute('''INSERT INTO inventory_invoice_lines
                (id,business_id,store_id,invoice_id,position,description,sku,product_id,package_id,quantity,unit,received,
                 product_name,base_unit,normalized_quantity,package_name,package_amount,product_version,package_version)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (item['id'], actor.business_id, actor.store_id, invoice_id, position, item['description'], item['sku'],
                 snap.get('productId'), snap.get('packageId'), item['quantity'], item['unit'], item['received'],
                 snap.get('productName'), snap.get('baseUnit'), snap.get('normalizedQuantity'), snap.get('packageName'),
                 snap.get('packageAmount'), snap.get('productVersion'), snap.get('packageVersion')))
        connection.execute('''UPDATE inventory_invoice_drafts SET supplier=%s,invoice_number=%s,
            version=version+%s,updated_at=NOW() WHERE id=%s''', (fields['supplier'], fields['invoiceNumber'], int(bump), invoice_id))

    def incoming_overflow(self, connection, actor):
        return connection.execute('''SELECT EXISTS(SELECT 1
            FROM inventory_invoice_lines l JOIN inventory_invoice_drafts d ON d.id=l.invoice_id
            WHERE d.business_id=%s AND d.store_id=%s AND d.state='draft' AND l.product_id IS NOT NULL
            GROUP BY l.product_id HAVING sum(l.normalized_quantity)>999999999999999.999999999)''',
            (actor.business_id, actor.store_id)).fetchone()[0]

    def close(self, connection, actor, invoice_id):
        connection.execute("UPDATE inventory_invoice_drafts SET state='closed',version=version+1,updated_at=NOW(),closed_by=%s,closed_at=NOW() WHERE id=%s",
                           (actor.user_id, invoice_id))

    def rebase(self, connection, invoice_id, baseline):
        connection.execute('UPDATE inventory_invoice_drafts SET baseline_count_id=%s,version=version+1,updated_at=NOW() WHERE id=%s',
                           (baseline, invoice_id))

    def incoming(self, connection, actor, query, after):
        after_name, after_id = after if after else (None, None)
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('''WITH incoming AS (
                  SELECT l.product_id,min(l.product_name) AS name,min(l.base_unit) AS base_unit,
                         sum(l.normalized_quantity) AS incoming_quantity,
                         sum(l.normalized_quantity) FILTER (WHERE l.received) AS received_quantity,
                         bool_or(CASE WHEN d.baseline_count_id IS NULL THEN EXISTS(
                           SELECT 1 FROM inventory_counts c WHERE c.store_id=d.store_id AND c.state='posted') ELSE EXISTS(
                           SELECT 1 FROM inventory_counts c JOIN inventory_counts b ON b.id=d.baseline_count_id
                           WHERE c.store_id=d.store_id AND c.state='posted' AND (c.posted_at,c.id)>(b.posted_at,b.id)) END) AS stale
                  FROM inventory_invoice_lines l JOIN inventory_invoice_drafts d ON d.id=l.invoice_id
                  JOIN inventory_products product ON product.business_id=l.business_id AND product.id=l.product_id
                  LEFT JOIN inventory_packages package ON package.business_id=l.business_id AND package.id=l.package_id
                  WHERE d.business_id=%s AND d.store_id=%s AND d.state='draft' AND l.product_id IS NOT NULL
                    AND product.active AND product.canonical_product_id IS NULL AND product.base_unit=l.base_unit
                    AND (l.package_id IS NULL OR (package.active AND package.product_id=l.product_id AND package.amount=l.package_amount))
                  GROUP BY l.product_id
                ) SELECT incoming.*,balance.quantity AS current_quantity
                FROM incoming LEFT JOIN inventory_stock_balances balance
                  ON balance.business_id=%s AND balance.store_id=%s AND balance.product_id=incoming.product_id
                 AND balance.base_unit=incoming.base_unit
                WHERE (%s='' OR strpos(lower(incoming.name),lower(%s))>0)
                  AND (%s::text IS NULL OR (lower(incoming.name) COLLATE "C",incoming.product_id)>(%s::text COLLATE "C",%s::uuid))
                ORDER BY lower(incoming.name) COLLATE "C",incoming.product_id LIMIT %s''',
                (actor.business_id, actor.store_id, actor.business_id, actor.store_id, query, query,
                 after_name, after_name, after_id, PAGE_SIZE + 1))
            rows = cursor.fetchall()
            cursor.execute('''SELECT count(*)::int AS unmatched_count FROM inventory_invoice_lines l JOIN inventory_invoice_drafts d ON d.id=l.invoice_id
                              WHERE d.business_id=%s AND d.store_id=%s AND d.state='draft' AND l.product_id IS NULL''',
                           (actor.business_id, actor.store_id))
            unmatched = cursor.fetchone()['unmatched_count']
            cursor.execute('''SELECT EXISTS(SELECT 1 FROM inventory_invoice_drafts d
                WHERE d.business_id=%s AND d.store_id=%s AND d.state='draft' AND
                  (CASE WHEN d.baseline_count_id IS NULL THEN EXISTS(
                    SELECT 1 FROM inventory_counts c WHERE c.store_id=d.store_id AND c.state='posted') ELSE EXISTS(
                    SELECT 1 FROM inventory_counts c JOIN inventory_counts b ON b.id=d.baseline_count_id
                    WHERE c.store_id=d.store_id AND c.state='posted' AND (c.posted_at,c.id)>(b.posted_at,b.id)) END)) AS stale''',
                (actor.business_id, actor.store_id))
            needs_count_review = cursor.fetchone()['stale']
            cursor.execute('''SELECT EXISTS(SELECT 1 FROM inventory_invoice_lines l
                JOIN inventory_invoice_drafts d ON d.id=l.invoice_id
                LEFT JOIN inventory_products p ON p.business_id=l.business_id AND p.id=l.product_id
                LEFT JOIN inventory_packages k ON k.business_id=l.business_id AND k.id=l.package_id
                WHERE d.business_id=%s AND d.store_id=%s AND d.state='draft' AND l.product_id IS NOT NULL AND (
                  p.id IS NULL OR NOT p.active OR p.canonical_product_id IS NOT NULL OR p.base_unit<>l.base_unit OR
                  (l.package_id IS NOT NULL AND (k.id IS NULL OR NOT k.active OR k.product_id<>l.product_id OR k.amount<>l.package_amount)))) AS stale''',
                (actor.business_id, actor.store_id))
            needs_catalog_review = cursor.fetchone()['stale']
        items = []
        for row in rows[:PAGE_SIZE]:
            current = row['current_quantity']
            items.append({'productId': str(row['product_id']), 'name': row['name'], 'baseUnit': row['base_unit'],
                          'currentQuantity': decimal_text(current) if current is not None else None,
                          'incomingQuantity': decimal_text(row['incoming_quantity']),
                          'receivedQuantity': decimal_text(row['received_quantity'] or 0),
                          'projectedQuantity': None if current is None or row['stale'] or current + row['incoming_quantity'] > MAX_STOCK
                                               else decimal_text(current + row['incoming_quantity'])})
        return {'items': items,
                'nextCursor': encode_product_cursor(rows[PAGE_SIZE-1]['name'].lower(), rows[PAGE_SIZE-1]['product_id']) if len(rows)>PAGE_SIZE else None,
                'unmatchedCount': unmatched, 'needsCountReview': needs_count_review,
                'needsCatalogReview': needs_catalog_review}
