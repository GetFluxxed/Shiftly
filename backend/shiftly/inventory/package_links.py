"""Owner-confirmed duplicate product consolidation before stock or recipe history.

The source identity, aliases and package rows are retained. New package rows live
under the target, while source rows point at them for canonical barcode lookup.
"""
from decimal import Decimal
from unicodedata import normalize
from uuid import uuid4

from psycopg.rows import dict_row

from backend.shiftly.identity.contracts import IdentityError
from . import validation as valid
from .packages import package as package_json
from .quantities import decimal_text

MAX_PACKAGE_AMOUNT = Decimal('999999999.999999999')
MAX_PACKAGES = 40
MAX_AUDIT_SCOPE_ROWS = 10_000


def _owner(actor):
    if actor.role != 'owner':
        raise IdentityError(
            'forbidden', 'Only the business owner can combine catalog products.',
            reason='permission_denied')


def _key(value):
    # PostgreSQL inventory_key uses NFKC, trim and lower.
    return normalize('NFKC', value).strip().lower()


def _convert(value, source_unit, target_unit):
    value = Decimal(value)
    if source_unit == target_unit:
        converted = value
    elif source_unit == 'g' and target_unit == 'kg':
        converted = value / Decimal('1000')
    elif source_unit == 'kg' and target_unit == 'g':
        converted = value * Decimal('1000')
    else:
        raise ValueError('incompatible')
    if converted <= 0 or converted > MAX_PACKAGE_AMOUNT or max(0, -converted.as_tuple().exponent) > 9:
        raise ValueError('precision')
    return converted


def _products(connection, business_id, source_id, target_id, *, lock=False):
    suffix = ' FOR UPDATE' if lock else ''
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('''SELECT * FROM inventory_products
            WHERE business_id=%s AND id=ANY(%s::uuid[]) ORDER BY id''' + suffix,
            (business_id, [source_id, target_id]))
        rows = {str(row['id']): row for row in cursor.fetchall()}
    return rows.get(source_id), rows.get(target_id)


def _packages(connection, business_id, product_id):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute('''SELECT p.*,COALESCE(array_agg(s.sku ORDER BY s.sku)
            FILTER (WHERE s.sku IS NOT NULL),'{}') AS barcodes
            FROM inventory_packages p LEFT JOIN inventory_product_skus s
              ON s.business_id=p.business_id AND s.product_id=p.product_id AND s.package_id=p.id
            WHERE p.business_id=%s AND p.product_id=%s
            GROUP BY p.id ORDER BY p.name_key,p.id''', (business_id, product_id))
        return cursor.fetchall()


def _history_issue(connection, business_id, product_ids):
    checks = (
        ('inventory_count_products', 'count snapshots'),
        ('inventory_stock_balances', 'stock balances'),
        ('inventory_stock_movements', 'stock movements'),
        ('production_recipe_ingredients', 'recipe revisions'),
    )
    found = []
    for table, label in checks:
        if connection.execute(
                f'SELECT 1 FROM {table} WHERE business_id=%s AND product_id=ANY(%s::uuid[]) LIMIT 1',
                (business_id, product_ids)).fetchone():
            found.append(label)
    return found


def _scope_state(connection, business_id, product_ids):
    listings = connection.execute('''SELECT store_id,product_id,active
        FROM inventory_store_products
        WHERE business_id=%s AND product_id=ANY(%s::uuid[])
        ORDER BY store_id,product_id LIMIT %s''',
        (business_id, product_ids, MAX_AUDIT_SCOPE_ROWS + 1)).fetchall()
    remaining = MAX_AUDIT_SCOPE_ROWS + 1 - len(listings)
    placements = connection.execute('''SELECT store_id,shelf_id,product_id,active
        FROM inventory_shelf_products
        WHERE business_id=%s AND product_id=ANY(%s::uuid[])
        ORDER BY store_id,shelf_id,product_id LIMIT %s''',
        (business_id, product_ids, max(1, remaining))).fetchall()
    if len(listings) + len(placements) > MAX_AUDIT_SCOPE_ROWS:
        raise IdentityError(
            'conflict', 'These products have too many store or shelf assignments to combine safely.',
            reason='state_conflict')
    return {
        'listings': [
            {'storeId': row[0], 'productId': str(row[1]), 'active': row[2]}
            for row in listings
        ],
        'placements': [
            {'storeId': row[0], 'shelfId': str(row[1]),
             'productId': str(row[2]), 'active': row[3]}
            for row in placements
        ],
    }


def _inspect(connection, service, actor, source_id, target_id, *, lock=False):
    issues = []
    if source_id == target_id:
        issues.append('Choose two different catalog products.')
    source, target = _products(connection, actor.business_id, source_id, target_id, lock=lock)
    if source is None:
        issues.append('The source product is not available in this business.')
    if target is None:
        issues.append('The target product is not available in this business.')
    if source is None or target is None:
        return source, target, [], 0, issues

    if not source['active'] or not target['active']:
        issues.append('Both products must be active before they can be combined.')
    if source['canonical_product_id'] is not None or target['canonical_product_id'] is not None:
        issues.append('A product already linked to a canonical product cannot be combined again.')
    if connection.execute('''SELECT 1 FROM inventory_products
            WHERE business_id=%s AND canonical_product_id=%s LIMIT 1''',
            (actor.business_id, source_id)).fetchone():
        issues.append('The source already has products linked to it. Resolve those links first to avoid a chain.')

    units = {source['base_unit'], target['base_unit']}
    if not (units <= {'g', 'kg'} or units == {'each'}):
        issues.append('Products can combine only when both use each, or both use mass units (g/kg).')

    source_packages = _packages(connection, actor.business_id, source_id)
    target_packages = _packages(connection, actor.business_id, target_id)
    if not source_packages:
        issues.append('Configure the source package size before combining these products.')
    default = next((row for row in source_packages if row['is_default']), None)
    current_alias = connection.execute('''SELECT package_id FROM inventory_product_skus
        WHERE business_id=%s AND product_id=%s AND sku_key=%s''',
        (actor.business_id, source_id, source['sku_key'])).fetchone()
    if default is None or current_alias is None or current_alias[0] is None or (
            default is not None and str(current_alias[0]) != str(default['id'])):
        issues.append('Link the source SKU to its default package before combining. Edit the package and add the source SKU as its barcode.')

    if len(source_packages) + len(target_packages) > MAX_PACKAGES:
        issues.append('The combined product would exceed the 40-package limit.')

    target_names = {_key(row['name']) for row in target_packages}
    proposed_names = []
    for row in source_packages:
        name = source['name'] if row['is_default'] else row['name']
        if row['is_default'] and len(name) > 120:
            issues.append('The source product name is too long for a package name. Shorten it to 120 characters before combining.')
        name_key = _key(name)
        if name_key in target_names or name_key in proposed_names:
            issues.append(f'The package name "{name}" conflicts on the target. Rename a package before combining.')
        proposed_names.append(name_key)
        try:
            _convert(row['amount'], source['base_unit'], target['base_unit'])
        except ValueError:
            issues.append(f'The package "{row["name"]}" cannot convert exactly to {target["base_unit"]} with at most 9 decimals.')

    product_ids = [source_id, target_id]
    history = _history_issue(connection, actor.business_id, product_ids)
    if history:
        issues.append('These products have ' + ', '.join(history) + '. Reconcile their history before combining them.')
    if connection.execute('''SELECT 1 FROM inventory_counts
            WHERE business_id=%s AND state IN ('draft','review') LIMIT 1''',
            (actor.business_id,)).fetchone():
        issues.append('Finish or cancel every open inventory count in this business before combining products.')
    scope_rows = connection.execute('''SELECT
        (SELECT count(*) FROM inventory_store_products
         WHERE business_id=%s AND product_id=ANY(%s::uuid[])) +
        (SELECT count(*) FROM inventory_shelf_products
         WHERE business_id=%s AND product_id=ANY(%s::uuid[]))''',
        (actor.business_id, product_ids, actor.business_id, product_ids)).fetchone()[0]
    if scope_rows > MAX_AUDIT_SCOPE_ROWS:
        issues.append('These products have too many store or shelf assignments to combine safely.')

    shelves = connection.execute('''SELECT count(*) FROM inventory_shelf_products
        WHERE business_id=%s AND product_id=%s AND active''',
        (actor.business_id, source_id)).fetchone()[0]
    return source, target, source_packages, shelves, issues


def _product(row):
    return {
        'id': str(row['id']), 'name': row['name'], 'sku': row['sku'],
        'baseUnit': row['base_unit'], 'active': row['active'], 'version': row['version'],
        'containerAmount': decimal_text(row['container_amount']) if row['container_amount'] is not None else None,
        'containerLabelAmount': decimal_text(row['container_label_amount']) if row['container_label_amount'] is not None else None,
        'containerLabelUnit': row['container_label_unit'],
    }


def preview(service, token, source_id, target_id):
    source_id, target_id = valid.identifier(source_id), valid.identifier(target_id)
    with service.connect() as connection:
        actor = service._actor(connection, token, 'catalog.manage')
        _owner(actor)
        source, target, packages, shelves, issues = _inspect(
            connection, service, actor, source_id, target_id)
        if source is None or target is None:
            raise IdentityError('not_found', 'Both catalog products must be available in this business.')
        return {
            'source': _product(source), 'target': _product(target),
            'sourceVersion': source['version'], 'targetVersion': target['version'],
            'packages': [package_json(row) for row in packages], 'shelves': shelves,
            'canCombine': not issues, 'issues': issues,
        }


def combine(service, token, source_id, fields):
    source_id = valid.identifier(source_id)
    target_id = valid.identifier(fields.get('targetProductId'))
    source_version = valid.version(fields.get('sourceVersion'))
    target_version = valid.version(fields.get('targetVersion'))
    if fields.get('confirmed') is not True:
        valid.invalid('Confirm the catalog combination after reviewing its effects.')
    payload = [source_id, target_id, source_version, target_version, True]

    def change(connection, actor):
        _owner(actor)
        source, target, source_packages, _, issues = _inspect(
            connection, service, actor, source_id, target_id, lock=True)
        if source is None or target is None:
            raise IdentityError('not_found', 'Both catalog products must be available in this business.')
        valid.current(_product(source), source_version)
        valid.current(_product(target), target_version)
        if issues:
            raise IdentityError('conflict', issues[0], reason='state_conflict')

        target_packages = _packages(connection, actor.business_id, target_id)
        before = {
            'source': _product(source), 'target': _product(target),
            'sourcePackages': [package_json(row) for row in source_packages],
            'targetPackages': [package_json(row) for row in target_packages],
            'scope': _scope_state(connection, actor.business_id, [source_id, target_id]),
        }

        copied = {}
        ordered = sorted(source_packages, key=lambda row: row['contained_package_id'] is not None)
        for row in ordered:
            new_id = str(uuid4())
            child = copied.get(str(row['contained_package_id'])) if row['contained_package_id'] else None
            if row['contained_package_id'] and child is None:
                raise IdentityError('conflict', 'The source case package is missing its contained package.', reason='state_conflict')
            child_id = child['id'] if child else None
            # Preserve the source row's recorded amount, including an archived
            # case whose leaf was deliberately edited later. Active cases are
            # already protected by the package integrity trigger.
            converted = _convert(row['amount'], source['base_unit'], target['base_unit'])
            name = source['name'] if row['is_default'] else row['name']
            connection.execute('''INSERT INTO inventory_packages
                (id,business_id,product_id,name,amount,kind,active,is_default,
                 contained_package_id,contained_count,label_amount,label_unit,version)
                VALUES(%s,%s,%s,%s,%s,%s,%s,false,%s,%s,%s,%s,1)''',
                (new_id, actor.business_id, target_id, name, decimal_text(converted),
                 row['kind'], row['active'], child_id, row['contained_count'],
                 row['label_amount'], row['label_unit']))
            copied[str(row['id'])] = {'id': new_id, 'amount': converted}

        # Archive cases before their leaves so the package integrity trigger never
        # observes an active case pointing at an inactive contained package.
        redirect_order = sorted(
            source_packages, key=lambda row: row['contained_package_id'] is None)
        for row in redirect_order:
            old_id = str(row['id'])
            new = copied[old_id]
            connection.execute('''UPDATE inventory_packages
                SET active=false,redirect_package_id=%s,version=version+1,updated_at=NOW()
                WHERE business_id=%s AND product_id=%s AND id=%s''',
                (new['id'], actor.business_id, source_id, old_id))

        connection.execute('''INSERT INTO inventory_store_products(business_id,store_id,product_id,active)
            SELECT business_id,store_id,%s,true FROM inventory_store_products
            WHERE business_id=%s AND product_id=%s AND active
            ON CONFLICT (business_id,store_id,product_id) DO UPDATE SET active=true''',
            (target_id, actor.business_id, source_id))
        affected = connection.execute('''SELECT store_id,shelf_id
            FROM inventory_shelf_products WHERE business_id=%s AND product_id=%s AND active
            ORDER BY store_id,shelf_id FOR UPDATE''', (actor.business_id, source_id)).fetchall()
        connection.execute('''INSERT INTO inventory_shelf_products
            (business_id,store_id,shelf_id,product_id,active)
            SELECT business_id,store_id,shelf_id,%s,true FROM inventory_shelf_products
            WHERE business_id=%s AND product_id=%s AND active
            ON CONFLICT (store_id,shelf_id,product_id)
            DO UPDATE SET active=true,updated_at=NOW()''',
            (target_id, actor.business_id, source_id))
        connection.execute('''UPDATE inventory_shelf_products SET active=false,updated_at=NOW()
            WHERE business_id=%s AND product_id=%s AND active''', (actor.business_id, source_id))
        connection.execute('''UPDATE inventory_store_products SET active=false
            WHERE business_id=%s AND product_id=%s AND active''', (actor.business_id, source_id))
        for store_id, shelf_id in affected:
            connection.execute('''UPDATE inventory_shelves SET version=version+1,updated_at=NOW()
                WHERE business_id=%s AND store_id=%s AND id=%s''',
                (actor.business_id, store_id, shelf_id))

        connection.execute('''UPDATE inventory_products
            SET active=false,canonical_product_id=%s,version=version+1,updated_at=NOW()
            WHERE business_id=%s AND id=%s''', (target_id, actor.business_id, source_id))
        connection.execute('''UPDATE inventory_products SET version=version+1,updated_at=NOW()
            WHERE business_id=%s AND id=%s''', (actor.business_id, target_id))
        saved_target = service.repository.product(connection, actor.business_id, target_id)
        saved_source = service.repository.product(connection, actor.business_id, source_id)
        after = {
            'source': saved_source, 'target': saved_target,
            'sourcePackages': service.package_options(connection, actor.business_id, source_id),
            'targetPackages': service.package_options(connection, actor.business_id, target_id),
            'scope': _scope_state(connection, actor.business_id, [source_id, target_id]),
        }
        return target_id, before, after, saved_target

    return service._write(
        token, fields, 'catalog.manage', 'product.combined', payload, change,
        authorize=_owner)
