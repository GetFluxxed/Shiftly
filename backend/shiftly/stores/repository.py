"""Existing store queries behind an explicit connection factory."""

from backend.shiftly.identity.primitives import hash_store_code


class StoresRepository:
    def __init__(self, connect):
        self.connect = connect

    def manager_username(self, manager_id):
        if not manager_id:
            return None
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT username FROM manager_users WHERE id = %s AND active", (manager_id,))
                row = cursor.fetchone()
        return row[0] if row else None

    def store_for_code(self, store_code):
        code_hash = hash_store_code(store_code)
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT id, name FROM stores WHERE access_code_hash = %s AND active", (code_hash,))
                row = cursor.fetchone()
        return row if row else None

    def heads_up(self, store_id):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT message, updated_at FROM store_heads_up WHERE store_id = %s", (store_id,))
                row = cursor.fetchone()
        return {"message": row[0], "updatedAt": row[1].isoformat()} if row else {"message": "", "updatedAt": None}

    def manager_accounts(self, store_id):
        with self.connect() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT m.username, m.last_sign_in_at
                    FROM manager_users m
                    JOIN store_memberships sm ON sm.manager_user_id = m.id AND sm.store_id = %s
                    WHERE m.active
                    ORDER BY m.last_sign_in_at DESC NULLS LAST, lower(m.username)
                    """,
                    (store_id,),
                )
                rows = cursor.fetchall()
        return [
            {"name": row[0], "lastSignIn": row[1].isoformat() if row[1] else None}
            for row in rows
        ]

    def save_heads_up(self, store_id, message, *, actor_token=None, accounts=None, legacy_credentials=None):
        with self.connect() as connection:
            if actor_token is not None:
                if accounts is None:
                    raise ValueError("Named changes require account authorization.")
                actor = accounts.require(actor_token, "reports.manage", connection=connection, store_id=store_id)
                accounts._audit(connection, actor, "heads_up.changed", store_id=store_id, business_id=actor.business_id)
            elif legacy_credentials is not None:
                from backend.shiftly.identity.repository import IdentityRepository
                IdentityRepository.authorize_legacy(connection, store_id, manager_required=True, **legacy_credentials)
            connection.execute("DELETE FROM store_heads_up WHERE store_id = %s", (store_id,))
            connection.execute("INSERT INTO store_heads_up (store_id, message, updated_at) VALUES (%s, %s, NOW())", (store_id, message))
            connection.commit()
        return self.heads_up(store_id)
