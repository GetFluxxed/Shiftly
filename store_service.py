import hashlib

from auth import is_manager, session_store_id
from database import db_connection
from security import cookie_token, hash_store_code


def manager_username(manager_id):
    if not manager_id:
        return None
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT username FROM manager_users WHERE id = %s AND active", (manager_id,))
            row = cursor.fetchone()
    return row[0] if row else None


def store_for_code(store_code):
    code_hash = hash_store_code(store_code)
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id, name FROM stores WHERE access_code_hash = %s AND active", (code_hash,))
            row = cursor.fetchone()
    return row if row else None


def heads_up(store_id):
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT message, updated_at FROM store_heads_up WHERE store_id = %s", (store_id,))
            row = cursor.fetchone()
    return {"message": row[0], "updatedAt": row[1].isoformat()} if row else {"message": "", "updatedAt": None}


def manager_accounts(store_id):
    with db_connection() as connection:
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


def is_crew(handler):
    cookie = cookie_token(handler, "shiftly_crew_session")
    if cookie:
        token_hash = hashlib.sha256(cookie.encode()).hexdigest()
        with db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM crew_sessions WHERE expires_at <= NOW()")
                cursor.execute(
                    """
                    SELECT cs.store_id
                    FROM crew_sessions cs
                    JOIN stores s ON s.id = cs.store_id AND s.active
                    WHERE cs.token_hash = %s AND cs.expires_at > NOW()
                    """,
                    (token_hash,),
                )
                row = cursor.fetchone()
            connection.commit()
        if row:
            return row[0]
    manager_id = is_manager(handler)
    return session_store_id(handler, manager_id) if manager_id else None
