"""PostgreSQL identity persistence; connection lifetimes are injected."""

from .primitives import hash_token


class IdentityRepository:
    def __init__(self, connect):
        self.connect = connect

    def manager_id(self, token):
        if not token:
            return False
        token_hash = hash_token(token)
        with self.connect() as connection:
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

    def selected_store(self, token, manager_id):
        if not manager_id:
            return None
        token_hash = hash_token(token)
        with self.connect() as connection:
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

    def crew_store(self, token):
        if token:
            token_hash = hash_token(token)
            with self.connect() as connection:
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


    def manager_credentials(self, store_id):
        with self.connect() as connection:
            return connection.execute(
                """SELECT m.id, m.password_salt, m.password_hash
                   FROM manager_users m
                   JOIN store_memberships sm ON sm.manager_user_id = m.id
                   WHERE sm.store_id = %s AND m.active""", (store_id,),
            ).fetchall()

    def crew_password_matches(self, store_id, candidate_hash):
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM stores WHERE id = %s AND crew_password_hash = %s AND active",
                (store_id, candidate_hash),
            ).fetchone() is not None

    @staticmethod
    def _session(connection, role, store_id, manager_id, token, ttl):
        token_hash = hash_token(token)
        if role == "crew":
            connection.execute(
                "INSERT INTO crew_sessions (token_hash, store_id, expires_at) VALUES (%s, %s, NOW() + (%s * INTERVAL '1 second'))",
                (token_hash, store_id, ttl),
            )
        else:
            connection.execute(
                "INSERT INTO manager_sessions (token_hash, manager_user_id, store_id, expires_at) VALUES (%s, %s, %s, NOW() + (%s * INTERVAL '1 second'))",
                (token_hash, manager_id, store_id, ttl),
            )
            connection.execute("UPDATE manager_users SET last_sign_in_at = NOW() WHERE id = %s", (manager_id,))

    def issue_session(self, role, store_id, manager_id, token, ttl):
        with self.connect() as connection:
            self._session(connection, role, store_id, manager_id, token, ttl)
            connection.commit()

    def create_account(self, *, store_id, store_name, code_hash, crew_hash,
                       manager_name, salt, password_hash, token, ttl):
        # Account, membership and first session succeed or roll back together.
        with self.connect() as connection:
            if store_id is None:
                store_id = connection.execute(
                    "INSERT INTO stores (name, access_code_hash, crew_password_hash) VALUES (%s, %s, %s) RETURNING id",
                    (store_name, code_hash, crew_hash),
                ).fetchone()[0]
            manager_id = connection.execute(
                "INSERT INTO manager_users (username, email, password_salt, password_hash) VALUES (%s, NULL, %s, %s) RETURNING id",
                (manager_name, salt, password_hash),
            ).fetchone()[0]
            connection.execute(
                "INSERT INTO store_memberships (manager_user_id, store_id, role) VALUES (%s, %s, 'manager')",
                (manager_id, store_id),
            )
            self._session(connection, "manager", store_id, manager_id, token, ttl)
            connection.commit()
        return manager_id, store_id

    def logout(self, manager_token, crew_token):
        with self.connect() as connection:
            if manager_token:
                connection.execute("DELETE FROM manager_sessions WHERE token_hash = %s", (hash_token(manager_token),))
            if crew_token:
                connection.execute("DELETE FROM crew_sessions WHERE token_hash = %s", (hash_token(crew_token),))
            connection.commit()
