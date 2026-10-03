"""Bounded correction of a catalog product's incorrectly chosen base unit.

Historical quantities are never converted.  A correction is available only while
the product has no count, stock, movement, production-log, or catalog-redirect
evidence that would make a new unit reinterpret an existing record.
"""
from uuid import uuid4

from psycopg.rows import dict_row

from backend.shiftly.identity.contracts import IdentityError
from . import validation as valid
from .quantities import package_amount
from .repository import product as product_json


HISTORY_CHECKS = (
    ('inventory_count_products', 'This product is already included in an inventory count.'),
    ('inventory_stock_balances', 'This product already has a stock balance.'),
    ('inventory_stock_movements', 'This product already has stock movement history.'),
    ('production_log_ingredients', 'This product is already included in a production log.'),
)

LINK_ISSUE = 'This product has catalog combination links that must remain unchanged.'
PACKAGE_ISSUE = 'This product has package options that cannot be inferred under a different base unit.'


def _conflict(message):
    raise IdentityError('conflict', message, reason='state_conflict')


def _product(connection, business_id, product_id, *, lock=False):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            '''SELECT * FROM inventory_products WHERE business_id=%s AND id=%s'''
            + (' FOR UPDATE' if lock else ''),
            (business_id, product_id),
        )
        return cursor.fetchone()


def _packages(connection, business_id, product_id, *, lock=False):
    with connection.cursor(row_factory=dict_row) as cursor:
        cursor.execute(
            '''SELECT * FROM inventory_packages
               WHERE business_id=%s AND product_id=%s ORDER BY id'''
            + (' FOR UPDATE' if lock else ''),
            (business_id, product_id),
        )
        return cursor.fetchall()


def _recipe_count(connection, business_id, product_id):
    return connection.execute(
        '''SELECT count(DISTINCT r.id)
           FROM production_recipes r
           JOIN production_recipe_ingredients i
             ON i.business_id=r.business_id AND i.recipe_id=r.id
            AND i.revision_id=r.current_revision_id
           WHERE r.business_id=%s AND i.product_id=%s''',
        (business_id, product_id),
    ).fetchone()[0]


def _issues(connection, business_id, product_id, row, packages):
    issues = []
    for table, message in HISTORY_CHECKS:
        if connection.execute(
            f'SELECT 1 FROM {table} WHERE business_id=%s AND product_id=%s LIMIT 1',
            (business_id, product_id),
        ).fetchone():
            issues.append(message)

    linked = row['canonical_product_id'] is not None or connection.execute(
        '''SELECT 1 FROM inventory_products
           WHERE business_id=%s AND canonical_product_id=%s LIMIT 1''',
        (business_id, product_id),
    ).fetchone() is not None
    redirected_package = any(package['redirect_package_id'] is not None for package in packages)
    if not redirected_package:
        redirected_package = connection.execute(
            '''SELECT 1 FROM inventory_packages source
               JOIN inventory_packages target
                 ON target.business_id=source.business_id AND target.id=source.redirect_package_id
               WHERE target.business_id=%s AND target.product_id=%s LIMIT 1''',
            (business_id, product_id),
        ).fetchone() is not None
    if linked or redirected_package:
        issues.append(LINK_ISSUE)

    if len(packages) > 1 or any(not package['is_default'] for package in packages):
        issues.append(PACKAGE_ISSUE)
    return issues


def _inspect(connection, actor, product_id, *, lock=False):
    row = _product(connection, actor.business_id, product_id, lock=lock)
    if row is None:
        raise IdentityError('not_found', 'This inventory record is not available in your current workspace.')
    packages = _packages(connection, actor.business_id, product_id, lock=lock)
    issues = _issues(connection, actor.business_id, product_id, row, packages)
    return row, packages, issues, _recipe_count(connection, actor.business_id, product_id)


def preview(service, token, product_id):
    product_id = valid.identifier(product_id)
    with service.connect() as connection:
        actor = service._actor(connection, token, 'catalog.manage')
        row, _, issues, recipe_count = _inspect(connection, actor, product_id)
        return {
            'product': product_json(row),
            'canChangeUnit': not issues,
            'issues': issues,
            'recipeCount': recipe_count,
        }


def correct(service, token, product_id, fields):
    product_id = valid.identifier(product_id)
    expected = valid.version(fields.get('version'))
    base_unit = fields.get('baseUnit')
    if base_unit not in valid.UNITS:
        valid.invalid('Choose items, grams or kilograms as the corrected base unit.')
    if 'containerAmount' not in fields:
        valid.invalid('Supply the corrected full-container amount, or null when no package is configured.')
    canonical, label, label_unit = package_amount(
        fields.get('containerAmount'), base_unit, fields.get('containerUnit'))
    acknowledged = fields.get('acknowledgeRecipes')
    if type(acknowledged) is not bool:
        valid.invalid('Recipe acknowledgement must be true or false.')

    payload = [product_id, expected, base_unit, canonical, label, label_unit, acknowledged]

    def change(connection, actor):
        row, packages, issues, recipe_count = _inspect(
            connection, actor, product_id, lock=True)
        before = product_json(row)
        valid.current(before, expected)
        if row['base_unit'] == base_unit:
            _conflict('The product already uses this base unit. Use the regular catalog editor for package changes.')
        if issues:
            _conflict(issues[0])
        if recipe_count and not acknowledged:
            _conflict('Acknowledge that current recipes keep their recorded ingredient units and must be reviewed separately.')

        default = packages[0] if packages else None
        # Package amounts have meaning only in their parent product's base unit.
        # Archiving an existing row would still leave an ambiguous historical
        # package under the corrected unit, so require its replacement amount.
        if default is not None and canonical is None:
            _conflict('Supply the full-container amount in the corrected unit so the existing package remains unambiguous.')

        mirror_amount = canonical if default is None or default['active'] else None
        mirror_label = label if mirror_amount is not None else None
        mirror_label_unit = label_unit if mirror_amount is not None else None
        connection.execute(
            '''UPDATE inventory_products SET base_unit=%s,container_amount=%s,
                   container_label_amount=%s,container_label_unit=%s,
                   version=version+1,updated_at=NOW()
               WHERE business_id=%s AND id=%s''',
            (base_unit, mirror_amount, mirror_label, mirror_label_unit,
             actor.business_id, product_id),
        )
        if default is not None:
            connection.execute(
                '''UPDATE inventory_packages SET amount=%s,label_amount=%s,label_unit=%s,
                       version=version+1,updated_at=NOW()
                   WHERE business_id=%s AND product_id=%s AND id=%s''',
                (canonical, label, label_unit, actor.business_id, product_id, default['id']),
            )
        elif canonical is not None:
            package_id = str(uuid4())
            service.package_repository.create(
                connection, actor.business_id, product_id, package_id,
                {'name': 'Container', 'amount': canonical, 'kind': 'container',
                 'labelAmount': label, 'labelUnit': label_unit},
                default=True,
            )
            connection.execute(
                '''UPDATE inventory_product_skus SET package_id=%s
                   WHERE business_id=%s AND product_id=%s AND package_id IS NULL''',
                (package_id, actor.business_id, product_id),
            )

        saved = service.repository.product(connection, actor.business_id, product_id)
        return product_id, before, saved, saved

    return service._write(
        token, fields, 'catalog.manage', 'product.measurement_corrected', payload, change)
