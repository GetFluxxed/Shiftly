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
                    LEFT JOIN account_users au ON au.legacy_manager_id = m.id
                    JOIN LATERAL (
                        SELECT sm.store_id
                        FROM store_memberships sm
                        JOIN stores s ON s.id = sm.store_id AND s.active
                        AND (s.business_id IS NULL OR EXISTS (SELECT 1 FROM businesses b WHERE b.id=s.business_id AND b.active))
                        WHERE sm.manager_user_id = m.id
                          AND (ms.store_id IS NULL OR sm.store_id = ms.store_id)
                        ORDER BY sm.store_id
                        LIMIT 1
                    ) active_membership ON TRUE
                    WHERE ms.token_hash = %s AND ms.expires_at > NOW()
                      AND (au.id IS NULL OR au.state = 'active')
                      AND NOT EXISTS (
                        SELECT 1 FROM account_store_memberships asm
                        WHERE asm.user_id = au.id AND asm.store_id = active_membership.store_id
                          AND asm.state <> 'active')
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
                    LEFT JOIN account_users au ON au.legacy_manager_id = m.id
                    LEFT JOIN LATERAL (
                        SELECT store_id
                        FROM store_memberships
                        WHERE manager_user_id = ms.manager_user_id
                          AND (ms.store_id IS NULL OR store_id = ms.store_id)
                        ORDER BY store_id
                        LIMIT 1
                    ) membership ON TRUE
                    JOIN stores s ON s.id = membership.store_id AND s.active
                      AND (s.business_id IS NULL OR EXISTS (SELECT 1 FROM businesses b WHERE b.id=s.business_id AND b.active))
                    WHERE ms.token_hash = %s AND ms.manager_user_id = %s AND ms.expires_at > NOW()
                      AND (au.id IS NULL OR au.state = 'active')
                      AND NOT EXISTS (
                        SELECT 1 FROM account_store_memberships asm
                        WHERE asm.user_id = au.id AND asm.store_id = membership.store_id
                          AND asm.state <> 'active')
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
                        JOIN stores s ON s.id = cs.store_id AND s.active AND s.shared_crew_enabled
                          AND (s.business_id IS NULL OR EXISTS (SELECT 1 FROM businesses b WHERE b.id=s.business_id AND b.active))
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
                   WHERE sm.store_id = %s AND m.active
                     AND NOT EXISTS (SELECT 1 FROM account_users au
                                     WHERE au.legacy_manager_id = m.id AND au.state <> 'active')
                     AND NOT EXISTS (SELECT 1 FROM account_store_memberships asm
                                     JOIN account_users au ON au.id = asm.user_id
                                     WHERE au.legacy_manager_id = m.id AND asm.store_id = sm.store_id
                                       AND asm.state <> 'active')""", (store_id,),
            ).fetchall()

    def crew_password_matches(self, store_id, candidate_hash):
        with self.connect() as connection:
            return connection.execute(
                "SELECT 1 FROM stores WHERE id = %s AND crew_password_hash = %s AND active AND shared_crew_enabled",
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

    def issue_session(self, role, store_id, manager_id, token, ttl, *, expected_salt=None, expected_hash=None):
        # The credential check may be expensive and precede this transaction.
        # Revalidate the exact verified generation under the shared policy lock
        # so password recovery/revocation cannot race a fresh legacy session.
        from .accounts_core import policy_lock
        from .service import IdentityError
        with self.connect() as connection:
            policy_lock(connection)
            store = connection.execute(
                """SELECT shared_crew_enabled,crew_password_hash FROM stores s WHERE id=%s AND active
                   AND (business_id IS NULL OR EXISTS (SELECT 1 FROM businesses b WHERE b.id=s.business_id AND b.active))""",
                (store_id,),
            ).fetchone()
            permitted = bool(store)
            if role == "crew":
                permitted = permitted and store[0] and expected_hash is not None and store[1] == expected_hash
            else:
                current = connection.execute(
                    """SELECT m.password_salt,m.password_hash FROM manager_users m
                       JOIN store_memberships sm ON sm.manager_user_id=m.id AND sm.store_id=%s
                       LEFT JOIN account_users au ON au.legacy_manager_id=m.id
                       LEFT JOIN account_store_memberships am ON am.user_id=au.id AND am.store_id=sm.store_id
                       WHERE m.id=%s AND m.active AND (au.id IS NULL OR au.state='active')
                         AND (am.user_id IS NULL OR am.state='active')""", (store_id,manager_id),
                ).fetchone()
                permitted = permitted and expected_hash is not None and current == (expected_salt,expected_hash)
            if not permitted:
                raise IdentityError("unauthenticated", "Credentials or access changed. Sign in again.")
            self._session(connection, role, store_id, manager_id, token, ttl)
            connection.commit()

    def create_account(self, *, store_id, store_name, code_hash, crew_hash,
                       manager_name, salt, password_hash, token, ttl):
        # Account, membership and first session succeed or roll back together.
        with self.connect() as connection:
            from .accounts_core import policy_lock
            from .service import IdentityError
            policy_lock(connection)
            if store_id is not None:
                row = connection.execute(
                    "SELECT business_id, accounts_enabled FROM stores WHERE id=%s FOR UPDATE", (store_id,)
                ).fetchone()
                if row and (row[0] is not None or row[1]):
                    raise IdentityError("forbidden", "Use named account administration for this store.")
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
            from .accounts_core import ensure_manager_account
            ensure_manager_account(connection, manager_id)
            self._session(connection, "manager", store_id, manager_id, token, ttl)
            connection.commit()
        return manager_id, store_id

    @staticmethod
    def authorize_legacy(connection, store_id, *, manager_token="", crew_token="", manager_required=False):
        """Recheck compatibility credentials in the transaction that posts a write."""
        from .accounts_core import policy_lock
        from .service import IdentityError
        policy_lock(connection)
        manager = None
        crew = None
        if manager_token:
            manager = connection.execute(
                """SELECT sm.store_id FROM manager_sessions ms
                   JOIN manager_users m ON m.id=ms.manager_user_id AND m.active
                   JOIN store_memberships sm ON sm.manager_user_id=m.id
                   JOIN stores s ON s.id=sm.store_id AND s.active
                   LEFT JOIN account_users au ON au.legacy_manager_id=m.id
                   LEFT JOIN account_store_memberships am ON am.user_id=au.id AND am.store_id=s.id
                   WHERE ms.token_hash=%s AND ms.expires_at>NOW()
                     AND (au.id IS NULL OR au.state='active') AND (am.user_id IS NULL OR am.state='active')
                     AND (s.business_id IS NULL OR EXISTS(SELECT 1 FROM businesses b WHERE b.id=s.business_id AND b.active))
                     AND (ms.store_id IS NULL OR ms.store_id=s.id)
                   ORDER BY s.id LIMIT 1""", (hash_token(manager_token),),
            ).fetchone()
        if crew_token:
            crew = connection.execute(
                """SELECT s.id FROM crew_sessions cs JOIN stores s ON s.id=cs.store_id
                   WHERE cs.token_hash=%s AND cs.expires_at>NOW() AND s.active AND s.shared_crew_enabled
                     AND (s.business_id IS NULL OR EXISTS(SELECT 1 FROM businesses b WHERE b.id=s.business_id AND b.active))""",
                (hash_token(crew_token),),
            ).fetchone()
        if manager and crew:
            raise IdentityError("unauthenticated", "Conflicting sign-in sessions. Sign in again.")
        effective = manager if manager_required else (manager or crew)
        if not effective or effective[0] != store_id:
            raise IdentityError("unauthenticated", "Session access changed. Sign in again.")

    def logout(self, manager_token, crew_token):
        with self.connect() as connection:
            if manager_token:
                connection.execute("DELETE FROM manager_sessions WHERE token_hash = %s", (hash_token(manager_token),))
            if crew_token:
                connection.execute("DELETE FROM crew_sessions WHERE token_hash = %s", (hash_token(crew_token),))
            connection.commit()
