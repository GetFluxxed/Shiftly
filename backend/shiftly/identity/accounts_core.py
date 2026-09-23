"""Framework-free named authentication, current-policy lookup and session control.

Public mutation methods own their transactions. Helpers supplied a connection
never commit; callers retain the policy lock through their associated write.
"""
import hmac
import re
import secrets
import unicodedata

from psycopg.types.json import Jsonb

from .admission import AdmissionControl
from .accounts_policy import AccountActor, capabilities_for
from .primitives import hash_store_code, hash_token, password_hash
from .contracts import IdentityError, SessionResult, require_store_context

ACCOUNT_COOKIE = "shiftly_account_session"


def policy_lock(connection):
    """Serialize policy mutation and authorized writes within this database schema.

    This deliberately favors a simple correct first release over fine-grained
    locks. The lock is database-wide across processes, not an in-memory mutex.
    """
    connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(current_schema() || ':accounts-policy', 0))")


def ensure_manager_account(connection, manager_id):
    """Copy an explicitly identified legacy manager, never match/merge by name.

    Existing named identity and revoked memberships are authoritative. This is
    also the compatibility hook for managers created after migration 014.
    """
    policy_lock(connection)
    manager = connection.execute(
        "SELECT username, password_salt, password_hash, active, created_at FROM manager_users WHERE id = %s",
        (manager_id,),
    ).fetchone()
    if not manager:
        raise IdentityError("not_found", "Manager account does not exist.")
    row = connection.execute("SELECT id FROM account_users WHERE legacy_manager_id = %s", (manager_id,)).fetchone()
    if row:
        user_id = row[0]
    else:
        # Unique normalized username constraint fails closed rather than choosing
        # one person when historical spellings collapse to the same identifier.
        collision = connection.execute(
            "SELECT 1 FROM account_users WHERE username_key = account_username_key(%s)", (manager[0],),
        ).fetchone()
        if collision:
            raise IdentityError("conflict", "Manager username requires operator reconciliation.")
        user_id = connection.execute(
            """INSERT INTO account_users
               (username, display_name, password_salt, password_hash, state, legacy_manager_id, created_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (manager[0], manager[0], manager[1], manager[2], "active" if manager[3] else "suspended", manager_id, manager[4]),
        ).fetchone()[0]
    # Only compatibility stores can accept legacy account creation. Activated
    # stores use named policy/lifecycle and cannot acquire authority by this hook.
    connection.execute(
        """INSERT INTO account_store_memberships (user_id, store_id, business_id, role, capabilities)
           SELECT %s, m.store_id, s.business_id, 'manager', ARRAY['reports.submit','reports.view','reports.manage']::TEXT[]
           FROM store_memberships m JOIN stores s ON s.id = m.store_id
           WHERE m.manager_user_id = %s AND NOT s.accounts_enabled
           ON CONFLICT (user_id, store_id) DO NOTHING""", (user_id, manager_id),
    )
    return user_id


class AccountCore:
    def __init__(self, connect, stores=None, *, admission=None,
                 token_factory=secrets.token_urlsafe, password_hasher=password_hash, session_ttl=28800):
        self.connect = connect
        self.stores = stores
        self.admission = admission if admission is not None else AdmissionControl()
        self.token_factory = token_factory
        self.password_hasher = password_hasher
        self.session_ttl = session_ttl

    _lock = staticmethod(policy_lock)

    @staticmethod
    def _validate_username(value):
        if not isinstance(value, str):
            raise IdentityError("invalid", "Username must be text.")
        value = re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()
        if not 2 <= len(value) <= 80 or any(ord(c) < 32 for c in value):
            raise IdentityError("invalid", "Username must contain 2 to 80 characters.")
        return value

    @staticmethod
    def _validate_password(value):
        if not isinstance(value, str) or not 8 <= len(value) <= 1024:
            raise IdentityError("invalid", "Password must contain 8 to 1024 characters.")
        return value

    @staticmethod
    def _validate_id(value):
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise IdentityError("invalid", "A valid numeric identifier is required.")
        return value

    @staticmethod
    def _audit(connection, actor, action, *, subject_user_id=None, store_id=None,
               business_id=None, reason="", details=None):
        actor_id = actor.user_id if isinstance(actor, AccountActor) else actor
        if isinstance(actor, AccountActor):
            store_id = actor.store_id if store_id is None else store_id
            business_id = actor.business_id if business_id is None else business_id
        connection.execute(
            """INSERT INTO account_audit
               (actor_user_id, subject_user_id, business_id, store_id, action, reason, details)
               VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (actor_id, subject_user_id, business_id, store_id, action, reason, Jsonb(details or {})),
        )

    def _actor_for_user(self, connection, user_id, store_id):
        row = connection.execute(
            """SELECT u.id,u.username,u.display_name,u.legacy_manager_id,u.credential_version,
                      s.id,s.business_id,s.accounts_enabled,b.active,
                      bm.role,bm.capabilities,sm.role,sm.capabilities,sm.business_id
               FROM account_users u
               JOIN stores s ON s.id = %s AND s.active
               LEFT JOIN businesses b ON b.id = s.business_id
               LEFT JOIN manager_users lm ON lm.id = u.legacy_manager_id
               LEFT JOIN business_memberships bm ON bm.user_id=u.id AND bm.business_id=s.business_id AND bm.state='active'
               LEFT JOIN account_store_memberships sm ON sm.user_id=u.id AND sm.store_id=s.id AND sm.state='active'
               WHERE u.id=%s AND u.state='active' AND (u.legacy_manager_id IS NULL OR lm.active)""",
            (store_id, user_id),
        ).fetchone()
        if not row:
            raise IdentityError("unauthenticated", "This account or store is unavailable.")
        (uid, username, display_name, legacy_id, version, sid, business_id, enabled,
         business_active, business_role, business_grants, store_role, store_grants, membership_business) = row
        if business_id is not None and not business_active:
            raise IdentityError("forbidden", "Business access is unavailable.", reason="access_changed")
        mapped = bool(business_id is not None and enabled)
        if business_role == "owner":
            role, grants = "owner", ()
        elif store_role and membership_business == business_id:
            role, grants = store_role, store_grants
            if role == "admin":
                if business_role != "admin":
                    raise IdentityError("forbidden", "Administrator delegation is unavailable.", reason="access_changed")
                grants = frozenset(grants) & frozenset(business_grants)
            if not mapped and legacy_id and role == "manager":
                if not connection.execute(
                    "SELECT 1 FROM store_memberships WHERE manager_user_id=%s AND store_id=%s", (legacy_id, sid),
                ).fetchone():
                    raise IdentityError("forbidden", "Store membership is unavailable.", reason="access_changed")
        else:
            raise IdentityError("forbidden", "No active membership for this store.", reason="access_changed")
        capabilities = capabilities_for(role, grants, mapped=mapped)
        # Shared catalog authority is a separate business-level delegation. A
        # local manager keeps that local role and gains no team/owner powers.
        if mapped and role == "manager" and business_role == "admin" and "catalog.manage" in business_grants:
            capabilities = capabilities | {"catalog.manage"}
        return AccountActor(uid, username, display_name, sid, business_id, role,
                            frozenset(capabilities), legacy_id, version)

    def resolve_actor(self, token, *, connection=None, capability=None, store_id=None):
        if not isinstance(token, str) or not token:
            raise IdentityError("unauthenticated", "Named sign-in is required.")
        if store_id is not None:
            self._validate_id(store_id)
        if connection is None:
            with self.connect() as owned:
                return self.resolve_actor(token, connection=owned, capability=capability, store_id=store_id)
        row = connection.execute(
            """SELECT a.user_id,a.store_id,a.credential_version
               FROM account_sessions a JOIN account_users u ON u.id=a.user_id
               WHERE a.token_hash=%s AND a.revoked_at IS NULL AND a.expires_at > NOW()
                 AND a.credential_version=u.credential_version AND u.state='active'""", (hash_token(token),),
        ).fetchone()
        if not row:
            raise IdentityError("unauthenticated", "Named session is invalid or expired.")
        actor = self._actor_for_user(connection, row[0], row[1])
        if actor.credential_version != row[2]:
            raise IdentityError("unauthenticated", "Named session is no longer current.")
        if store_id is not None and store_id != actor.store_id:
            actor = self._actor_for_user(connection, actor.user_id, store_id)
        if capability and capability not in actor.capabilities:
            raise IdentityError("forbidden", "This account lacks the required permission.", reason="permission_denied")
        return actor

    def require(self, token, capability, *, connection, store_id=None):
        self._lock(connection)
        return self.resolve_actor(token, connection=connection, capability=capability, store_id=store_id)

    def require_selected_store(self, token, capability, *, connection, expected_store_id):
        """Authorize a feature transaction without letting a request retarget it.

        The caller retains the policy lock until its write and feature audit
        commit together. This method never commits on the caller's behalf.
        """
        actor = self.require(token, capability, connection=connection)
        require_store_context(actor, expected_store_id)
        return actor

    def authorized_stores(self, token, *, capability=None, connection=None):
        if connection is None:
            with self.connect() as owned:
                return self.authorized_stores(token, capability=capability, connection=owned)
        selected = self.resolve_actor(token, connection=connection)
        candidates = connection.execute(
            """SELECT DISTINCT s.id,s.name FROM stores s
               LEFT JOIN account_store_memberships sm ON sm.store_id=s.id AND sm.user_id=%s AND sm.state='active'
               LEFT JOIN business_memberships bm ON bm.business_id=s.business_id AND bm.user_id=%s AND bm.state='active' AND bm.role='owner'
               WHERE s.active AND (sm.user_id IS NOT NULL OR bm.user_id IS NOT NULL) ORDER BY s.id""",
            (selected.user_id, selected.user_id),
        ).fetchall()
        result = []
        for sid, name in candidates:
            try:
                actor = self._actor_for_user(connection, selected.user_id, sid)
            except IdentityError:
                continue
            if not capability or capability in actor.capabilities:
                result.append({**actor.as_dict(), "storeName": name})
        return result

    def login_payload(self, fields, *, client_key):
        if not isinstance(fields, dict):
            raise IdentityError("invalid", "Invalid named sign-in request.")
        return self.login(fields.get("storeCode"), fields.get("username"), fields.get("password"), client_key=client_key)

    def login(self, store_code, username, password, *, client_key):
        if not isinstance(store_code, str) or not store_code.strip() or len(store_code) > 40:
            raise IdentityError("invalid", "A store code is required.")
        username = self._validate_username(username)
        if not isinstance(password, str) or not password or len(password) > 1024:
            raise IdentityError("unauthenticated", "Incorrect store code, username or password.")
        store_code = store_code.strip()
        if not self.admission.reserve_login(client_key, store_code):
            raise IdentityError("limited", "Too many failed sign-in attempts. Try again later.")
        success = False
        try:
            with self.connect() as connection:
                self._lock(connection)
                store = connection.execute(
                    "SELECT id FROM stores WHERE access_code_hash=%s AND active", (hash_store_code(store_code),),
                ).fetchone()
                if not store:
                    raise IdentityError("unauthenticated", "Incorrect store code, username or password.")
                # This compatibility lookup identifies a manager by its unique ID;
                # it never chooses a manager by password or merges username matches.
                managers = connection.execute(
                    "SELECT id FROM manager_users WHERE account_username_key(username)=account_username_key(%s)", (username,),
                ).fetchall()
                if len(managers) > 1:
                    raise IdentityError("conflict", "Manager username requires operator reconciliation.")
                if managers:
                    ensure_manager_account(connection, managers[0][0])
                row = connection.execute(
                    """SELECT id,password_salt,password_hash FROM account_users
                       WHERE username_key=account_username_key(%s) AND state='active'""", (username,),
                ).fetchone()
                if not row or not hmac.compare_digest(row[2], self.password_hasher(password, row[1])):
                    raise IdentityError("unauthenticated", "Incorrect store code, username or password.")
                try:
                    result = self._issue_session(connection, row[0], store[0])
                except IdentityError as error:
                    if error.code in {"forbidden", "unauthenticated"}:
                        raise IdentityError("unauthenticated", "Incorrect store code, username or password.") from error
                    raise
                self._audit(connection, row[0], "session.login", store_id=store[0])
            success = True
            return result
        finally:
            self.admission.finish_login(client_key, store_code, failed=not success)

    def _issue_session(self, connection, user_id, store_id):
        actor = self._actor_for_user(connection, user_id, store_id)
        token = self.token_factory(32)
        connection.execute(
            """INSERT INTO account_sessions (token_hash,user_id,store_id,credential_version,expires_at)
               VALUES (%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 second'))""",
            (hash_token(token), user_id, store_id, actor.credential_version, self.session_ttl),
        )
        store_name = connection.execute("SELECT name FROM stores WHERE id=%s", (store_id,)).fetchone()[0]
        response = {"authenticated": True, "role": "crew" if actor.role == "crew" else "manager",
                    "actor": actor.as_dict(), "storeName": store_name}
        if actor.role != "crew":
            response["managerName"] = actor.display_name
        if actor.legacy_manager_id:
            connection.execute("UPDATE manager_users SET last_sign_in_at=NOW() WHERE id=%s", (actor.legacy_manager_id,))
        return SessionResult("account", token, response, self.session_ttl)

    def switch_store(self, token, store_id):
        self._validate_id(store_id)
        with self.connect() as connection:
            self._lock(connection)
            actor = self.resolve_actor(token, connection=connection)
            target = self._actor_for_user(connection, actor.user_id, store_id)
            # Rotate the bearer token so a copy of the old selected-store token
            # cannot continue to operate under the new context.
            result = self._issue_session(connection, target.user_id, target.store_id)
            connection.execute("UPDATE account_sessions SET revoked_at=NOW() WHERE token_hash=%s", (hash_token(token),))
            self._audit(connection, actor, "session.switch_store", store_id=store_id, business_id=target.business_id)
            return result

    def logout(self, token):
        if not isinstance(token, str) or not token:
            return {"authenticated": False}
        with self.connect() as connection:
            self._lock(connection)
            row = connection.execute(
                """UPDATE account_sessions SET revoked_at=NOW()
                   WHERE token_hash=%s AND revoked_at IS NULL RETURNING user_id,store_id""", (hash_token(token),),
            ).fetchone()
            if row:
                self._audit(connection, row[0], "session.logout", store_id=row[1])
        return {"authenticated": False}

    @staticmethod
    def _revoke_user_sessions(connection, user_id, store_id=None):
        connection.execute(
            """UPDATE account_sessions SET revoked_at=NOW() WHERE user_id=%s AND revoked_at IS NULL
               AND (%s::BIGINT IS NULL OR store_id=%s)""", (user_id, store_id, store_id),
        )
        connection.execute(
            """DELETE FROM manager_sessions WHERE manager_user_id=(SELECT legacy_manager_id FROM account_users WHERE id=%s)
               AND (%s::BIGINT IS NULL OR store_id=%s OR store_id IS NULL)""", (user_id, store_id, store_id),
        )

    def logout_all(self, token):
        with self.connect() as connection:
            self._lock(connection)
            actor = self.resolve_actor(token, connection=connection)
            self._revoke_user_sessions(connection, actor.user_id)
            self._audit(connection, actor, "session.logout_all", subject_user_id=actor.user_id)
        return {"authenticated": False}
