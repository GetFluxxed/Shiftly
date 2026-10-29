"""One stock projection and append-only history for counts and production.

The caller owns authorization and the transaction. Lock the store before reading
baselines or making mutations; this also serializes products with no balance yet.
"""
from decimal import Decimal
from uuid import uuid4

from psycopg.rows import dict_row

from backend.shiftly.identity.contracts import IdentityError

MAX_QUANTITY = Decimal('999999999999999.999999999')


def bounded(quantity):
    if not isinstance(quantity, Decimal) or not quantity.is_finite() or not 0 <= quantity <= MAX_QUANTITY:
        raise IdentityError('invalid', 'The resulting stock quantity is outside the supported range.')
    if quantity != quantity.quantize(Decimal('0.000000001')):
        raise IdentityError('invalid', 'This quantity needs more than nine decimal places. Adjust the recipe measurement.')
    return quantity.quantize(Decimal('0.000000001')).normalize()


class MovementRepository:
    @staticmethod
    def lock_store(connection, actor):
        connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':' || %s,0))",
                           (f'inventory-stock:{actor.business_id}:{actor.store_id}',))

    @staticmethod
    def balances(connection, actor, product_ids):
        if not product_ids:
            return {}
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("""SELECT * FROM inventory_stock_balances
                WHERE business_id=%s AND store_id=%s AND product_id=ANY(%s::uuid[])
                ORDER BY product_id FOR UPDATE""", (actor.business_id,actor.store_id,list(map(str,product_ids))))
            return {str(row['product_id']):row for row in cursor.fetchall()}

    def apply(self, connection, actor, *, product_id, base_unit, quantity_after,
              kind, source_id, reverses_id=None, count_id=None, counted_on=None):
        after = bounded(quantity_after)
        before = self.balances(connection,actor,[product_id]).get(str(product_id))
        if kind not in ('opening','count','production','reversal'):
            raise ValueError('Unknown stock movement kind')
        if before and before['base_unit'] != base_unit:
            raise IdentityError('conflict','The stock unit changed. Reload before continuing.',reason='state_conflict')
        if not before and kind not in ('opening','count'):
            raise IdentityError('conflict','Complete an opening inventory count before recording production.',reason='state_conflict')
        if kind in ('opening','count'):
            kind = 'opening' if before is None else 'count'
            if not count_id or not counted_on:
                raise ValueError('Physical stock movements require count evidence')
        if kind == 'production' and after >= before['quantity']:
            raise ValueError('Production must consume stock')
        if kind == 'reversal':
            original = connection.execute("""SELECT delta,kind FROM inventory_stock_movements
                WHERE id=%s AND business_id=%s AND store_id=%s AND product_id=%s AND base_unit=%s""",
                (reverses_id,actor.business_id,actor.store_id,product_id,base_unit)).fetchone()
            if not original or original[1]!='production' or after-before['quantity'] != -original[0]:
                raise IdentityError('conflict','This reversal does not match the original production deduction.',reason='state_conflict')
        movement_id = str(uuid4())
        version = before['version']+1 if before else 1
        connection.execute("""INSERT INTO inventory_stock_movements(id,business_id,store_id,product_id,base_unit,kind,
            source_id,quantity_before,quantity_after,version,reverses_id,actor_user_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (movement_id,actor.business_id,actor.store_id,product_id,base_unit,kind,source_id,
             before['quantity'] if before else None,after,version,reverses_id,actor.user_id))
        if kind in ('opening','count'):
            connection.execute("""INSERT INTO inventory_stock_balances(business_id,store_id,product_id,count_id,
                quantity,base_unit,counted_on,version,last_movement_id,last_counted_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW()) ON CONFLICT(business_id,store_id,product_id)
                DO UPDATE SET count_id=EXCLUDED.count_id,quantity=EXCLUDED.quantity,base_unit=EXCLUDED.base_unit,
                counted_on=EXCLUDED.counted_on,updated_at=NOW(),version=EXCLUDED.version,
                last_movement_id=EXCLUDED.last_movement_id,last_counted_at=NOW()""",
                (actor.business_id,actor.store_id,product_id,count_id,after,base_unit,counted_on,version,movement_id))
        else:
            connection.execute("""UPDATE inventory_stock_balances SET quantity=%s,updated_at=NOW(),
                version=%s,last_movement_id=%s WHERE business_id=%s AND store_id=%s AND product_id=%s""",
                (after,version,movement_id,actor.business_id,actor.store_id,product_id))
        return movement_id
