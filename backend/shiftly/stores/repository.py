"""Existing store queries behind an explicit connection factory."""

from backend.shiftly.identity.primitives import hash_store_code
from backend.shiftly.identity.contracts import IdentityError


def require_heads_up(actor, *, writing=False):
    allowed = {"manager"} if writing else {"manager", "crew", "production"}
    if actor.role not in allowed:
        message = "Only store managers can update Heads Up." if writing else "Heads Up is available to store managers, crew and production."
        raise IdentityError("forbidden", message, reason="permission_denied")



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

    def heads_up(self, store_id, *, actor_token=None, accounts=None):
        with self.connect() as connection:
            if actor_token is not None:
                if accounts is None:
                    raise ValueError("Named reads require account authorization.")
                actor = accounts.require_selected_store(actor_token, None, connection=connection, expected_store_id=store_id)
                require_heads_up(actor)
                store_id = actor.store_id
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
                actor = accounts.require_selected_store(actor_token, "reports.manage", connection=connection, expected_store_id=store_id)
                require_heads_up(actor, writing=True)
                store_id = actor.store_id
                accounts._audit(connection, actor, "heads_up.changed", store_id=store_id, business_id=actor.business_id)
            elif legacy_credentials is not None:
                from backend.shiftly.identity.repository import IdentityRepository
                IdentityRepository.authorize_legacy(connection, store_id, manager_required=True, **legacy_credentials)
            row = connection.execute(
                """INSERT INTO store_heads_up (store_id, message, updated_at) VALUES (%s, %s, NOW())
                   ON CONFLICT (store_id) DO UPDATE SET message=EXCLUDED.message, updated_at=EXCLUDED.updated_at
                   RETURNING message, updated_at""", (store_id, message),
            ).fetchone()
            connection.commit()
        return {"message": row[0], "updatedAt": row[1].isoformat()}
