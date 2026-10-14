"""Package catalog SQL and exact package serialization."""
from psycopg.rows import dict_row

from .quantities import decimal_text


def package(row):
    return {
        'id': str(row['id']), 'productId': str(row['product_id']), 'name': row['name'],
        'amount': decimal_text(row['amount']),
        'labelAmount': decimal_text(row['label_amount']) if row['label_amount'] is not None else None,
        'labelUnit': row['label_unit'], 'kind': row['kind'], 'active': row['active'],
        'version': row['version'], 'isDefault': row['is_default'],
        'containedPackageId': str(row['contained_package_id']) if row['contained_package_id'] else None,
        'containedCount': row['contained_count'], 'barcodes': list(row.get('barcodes') or ()),
    }


class PackageRepository:
    SELECT = '''SELECT p.*,COALESCE(array_agg(s.sku ORDER BY s.sku)
        FILTER (WHERE s.sku IS NOT NULL),'{}') AS barcodes
        FROM inventory_packages p LEFT JOIN inventory_packages alias_package
        ON alias_package.business_id=p.business_id
          AND (alias_package.id=p.id OR alias_package.redirect_package_id=p.id)
        LEFT JOIN inventory_product_skus s
        ON s.business_id=p.business_id AND s.package_id=alias_package.id'''

    def packages(self, connection, business_id, product_id, active_only=False):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(self.SELECT + ''' WHERE p.business_id=%s AND p.product_id=%s
                AND (NOT %s OR p.active) GROUP BY p.id ORDER BY p.name_key,p.id LIMIT 41''',
                           (business_id, product_id, active_only))
            return [package(row) for row in cursor.fetchall()]

    def one(self, connection, business_id, product_id, package_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(self.SELECT + ''' WHERE p.business_id=%s AND p.product_id=%s AND p.id=%s
                GROUP BY p.id''', (business_id, product_id, package_id))
            row = cursor.fetchone()
            return package(row) if row else None

    def raw(self, connection, business_id, product_id, package_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('SELECT * FROM inventory_packages WHERE business_id=%s AND product_id=%s AND id=%s FOR UPDATE',
                           (business_id, product_id, package_id))
            return cursor.fetchone()

    def default(self, connection, business_id, product_id):
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute('''SELECT * FROM inventory_packages WHERE business_id=%s AND product_id=%s
                AND is_default FOR UPDATE''', (business_id,product_id))
            return cursor.fetchone()

    def create(self, connection, business_id, product_id, package_id, data, *, default=False):
        connection.execute('''INSERT INTO inventory_packages
            (id,business_id,product_id,name,amount,kind,is_default,contained_package_id,contained_count,label_amount,label_unit)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
            (package_id,business_id,product_id,data['name'],data['amount'],data['kind'],default,
             data.get('containedPackageId'),data.get('containedCount'),data.get('labelAmount'),data.get('labelUnit')))

    def edit(self, connection, business_id, product_id, package_id, data):
        connection.execute('''UPDATE inventory_packages SET name=%s,amount=%s,kind=%s,
            contained_package_id=%s,contained_count=%s,label_amount=%s,label_unit=%s,version=version+1,updated_at=NOW()
            WHERE business_id=%s AND product_id=%s AND id=%s''',
            (data['name'],data['amount'],data['kind'],data.get('containedPackageId'),data.get('containedCount'),
             data.get('labelAmount'),data.get('labelUnit'),
             business_id,product_id,package_id))

    def state(self, connection, business_id, product_id, package_id, active):
        connection.execute('''UPDATE inventory_packages SET active=%s,version=version+1,updated_at=NOW()
            WHERE business_id=%s AND product_id=%s AND id=%s''',
            (active,business_id,product_id,package_id))

    def referencing_case(self, connection, business_id, product_id, package_id):
        return connection.execute('''SELECT 1 FROM inventory_packages WHERE business_id=%s AND product_id=%s
            AND contained_package_id=%s AND active LIMIT 1''', (business_id,product_id,package_id)).fetchone() is not None

    def bump_product(self, connection, business_id, product_id, amount_marker=None, *, sync_default=False,
                     label_amount=None, label_unit=None):
        if not sync_default:
            connection.execute('UPDATE inventory_products SET version=version+1,updated_at=NOW() WHERE business_id=%s AND id=%s',
                               (business_id,product_id))
        else:
            connection.execute('''UPDATE inventory_products SET container_amount=%s,container_label_amount=%s,
                container_label_unit=%s,version=version+1,updated_at=NOW()
                WHERE business_id=%s AND id=%s''', (amount_marker,label_amount,label_unit,business_id,product_id))

    def assign_alias(self, connection, business_id, product_id, package_id, sku):
        row = connection.execute('''SELECT s.product_id,s.package_id,p.canonical_product_id,k.redirect_package_id
            FROM inventory_product_skus s
            JOIN inventory_products p ON p.business_id=s.business_id AND p.id=s.product_id
            LEFT JOIN inventory_packages k ON k.business_id=s.business_id AND k.id=s.package_id
            WHERE s.business_id=%s AND s.sku_key=inventory_key(%s) FOR UPDATE OF s''',
            (business_id,sku)).fetchone()
        if row:
            direct = str(row[0]) == product_id and (row[1] is None or str(row[1]) == package_id)
            redirected = (row[2] is not None and str(row[2]) == product_id
                          and row[3] is not None and str(row[3]) == package_id)
            if not direct and not redirected:
                return False
            if redirected:
                return True
            connection.execute('UPDATE inventory_product_skus SET package_id=%s WHERE business_id=%s AND sku_key=inventory_key(%s)',
                               (package_id,business_id,sku))
            return True
        connection.execute('INSERT INTO inventory_product_skus(business_id,product_id,sku,package_id) VALUES(%s,%s,%s,%s)',
                           (business_id,product_id,sku,package_id))
        return True
