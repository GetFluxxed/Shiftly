import hashlib

from database import db_connection
from security import cookie_token

def is_manager(handler):
    cookie = cookie_token(handler, "shiftly_manager_session")
    if not cookie:
        return False
    token_hash = hashlib.sha256(cookie.encode()).hexdigest()
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM manager_sessions WHERE expires_at <= NOW()")
            cursor.execute(
                """
                SELECT ms.manager_user_id
                FROM manager_sessions ms
                JOIN manager_users m ON m.id = ms.manager_user_id AND m.active
                JOIN LATERAL (
                    SELECT sm.store_id
                    FROM store_memberships sm
                    JOIN stores s ON s.id = sm.store_id AND s.active
                    WHERE sm.manager_user_id = m.id
                      AND (ms.store_id IS NULL OR sm.store_id = ms.store_id)
                    ORDER BY sm.store_id
                    LIMIT 1
                ) active_membership ON TRUE
                WHERE ms.token_hash = %s AND ms.expires_at > NOW()
                """,
                (token_hash,),
            )
            row = cursor.fetchone()
        connection.commit()
    return row[0] if row else None


def session_store_id(handler, manager_id):
    if not manager_id:
        return None
    cookie = cookie_token(handler, "shiftly_manager_session")
    token_hash = hashlib.sha256(cookie.encode()).hexdigest()
    with db_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT membership.store_id
                FROM manager_sessions ms
                JOIN manager_users m ON m.id = ms.manager_user_id AND m.active
                LEFT JOIN LATERAL (
                    SELECT store_id
                    FROM store_memberships
                    WHERE manager_user_id = ms.manager_user_id
                      AND (ms.store_id IS NULL OR store_id = ms.store_id)
                    ORDER BY store_id
                    LIMIT 1
                ) membership ON TRUE
                JOIN stores s ON s.id = membership.store_id AND s.active
                WHERE ms.token_hash = %s AND ms.manager_user_id = %s AND ms.expires_at > NOW()
                """,
                (token_hash, manager_id),
            )
            row = cursor.fetchone()
            if row and row[0]:
                cursor.execute(
                    "UPDATE manager_sessions SET store_id = %s WHERE token_hash = %s",
                    (row[0], token_hash),
                )
        connection.commit()
    return row[0] if row else None
