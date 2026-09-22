"""Account and session workflows independent of HTTP handlers."""

import hmac
import secrets
from dataclasses import dataclass, field

import psycopg

from .admission import AdmissionControl
from .primitives import clean, hash_store_code, password_hash


class IdentityError(Exception):
    """Stable domain reason; HTTP adapters translate code into a status."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SessionResult:
    role: str
    token: str = field(repr=False)
    response: dict
    ttl: int


class IdentityService:
    def __init__(self, repository, stores, *, admin_key="", session_ttl=28800,
                 admission=None, token_factory=secrets.token_urlsafe,
                 password_hasher=password_hash, store_lookup=None, username_lookup=None, accounts=None):
        self.repository = repository
        self._accounts = accounts
        self.stores = stores
        self.admin_key = admin_key
        self.session_ttl = session_ttl
        self.admission = admission if admission is not None else AdmissionControl()
        self.token_factory = token_factory
        self.password_hasher = password_hasher
        self.store_lookup = store_lookup if store_lookup is not None else stores.store_for_code
        self.username_lookup = username_lookup if username_lookup is not None else stores.manager_username

    @property
    def accounts(self):
        if self._accounts is None:
            from .accounts import AccountsService
            self._accounts = AccountsService(
                self.repository.connect, self.stores, admission=self.admission,
                token_factory=self.token_factory, password_hasher=self.password_hasher,
                session_ttl=self.session_ttl,
            )
        return self._accounts

    def resolve_principal(self, *, account_token=None, manager_token="", crew_token=""):
        from .principal import resolve_principal
        return resolve_principal(self, account_token=account_token,
                                 manager_token=manager_token, crew_token=crew_token)

    def manager_id(self, token):
        return self.repository.manager_id(token)

    def selected_store(self, manager_token, manager_id):
        return self.repository.selected_store(manager_token, manager_id)

    def crew_store(self, crew_token, manager_token=""):
        store_id = self.repository.crew_store(crew_token)
        if store_id:
            return store_id
        manager_id = self.manager_id(manager_token)
        return self.selected_store(manager_token, manager_id) if manager_id else None

    def logout(self, manager_token="", crew_token=""):
        self.repository.logout(manager_token, crew_token)

    def login_payload(self, fields, *, client_key):
        try:
            raw_code = fields.get("storeCode")
            if raw_code is not None and not isinstance(raw_code, str):
                raise ValueError("Store code must be text.")
            code = clean(raw_code, 40)
            role = str(fields.get("role", "auto")).strip().casefold()
            password = str(fields.get("password", ""))
        except (ValueError, TypeError, UnicodeError) as error:
            raise IdentityError("invalid", "Invalid login request.") from error
        return self.login(code, role, password, client_key=client_key)

    def login(self, store_code, role, password, *, client_key):
        if role not in {"auto", "crew", "manager"}:
            raise IdentityError("invalid", "Invalid sign-in role.")
        if not self.admission.reserve_login(client_key, store_code):
            raise IdentityError("limited", "Too many failed sign-in attempts. Try again later.")
        authenticated = False
        try:
            result = self._login_reserved(store_code, role, password)
            authenticated = True
            return result
        finally:
            self.admission.finish_login(client_key, store_code, failed=not authenticated)

    def _login_reserved(self, store_code, role, password):
        store = self.store_lookup(store_code)
        if not store or not password:
            raise IdentityError("unauthenticated", "Incorrect store code or password.")
        store_id, store_name = store
        if role == "auto":
            credentials = self.repository.manager_credentials(store_id)
            role = "manager" if any(
                hmac.compare_digest(candidate_hash, self.password_hasher(password, salt))
                for _, salt, candidate_hash in credentials
            ) else "crew"
        manager_id = None
        verified_salt = None
        if role == "crew":
            candidate_hash = self.password_hasher(password, f"shiftly-crew:{hash_store_code(store_code)}")
            if not self.repository.crew_password_matches(store_id, candidate_hash):
                raise IdentityError("unauthenticated", "Incorrect store code or password.")
        else:
            candidates = self.repository.manager_credentials(store_id)
            manager = next((candidate for candidate in candidates if hmac.compare_digest(
                candidate[2], self.password_hasher(password, candidate[1]),
            )), None)
            if not manager:
                raise IdentityError("unauthenticated", "Incorrect store code or password.")
            manager_id = manager[0]
            verified_salt, candidate_hash = manager[1], manager[2]
        token = self.token_factory(32)
        self.repository.issue_session(role, store_id, manager_id, token, self.session_ttl,
                                      expected_salt=verified_salt, expected_hash=candidate_hash)
        response = {"authenticated": True, "role": role}
        if manager_id is not None:
            response["managerName"] = self.username_lookup(manager_id)
        response["storeName"] = store_name
        return SessionResult(role, token, response, self.session_ttl)

    def require_account_creation(self, *, action="signup"):
        if not self.admin_key:
            message = "Workspace creation is not configured." if action == "signup" else "Manager creation is not configured."
            raise IdentityError("unavailable", message)

    def admit_account_creation(self, client_key, *, action="signup"):
        """Call before parsing the body to preserve config/rate-limit ordering."""
        self.require_account_creation(action=action)
        if not self.admission.admit_signup(client_key):
            message = "Too many sign-up attempts. Try again later." if action == "signup" else "Too many account creation attempts. Try again later."
            raise IdentityError("limited", message)

    def signup(self, fields):
        return self._create_account(fields, new_store=True)

    def add_manager(self, fields):
        return self._create_account(fields, new_store=False)

    def _create_account(self, fields, *, new_store):
        self.require_account_creation(action="signup" if new_store else "add_manager")
        store_name = clean(fields.get("storeName"), 120) if new_store else None
        store_code = clean(fields.get("storeCode"), 40)
        crew_password = str(fields.get("crewPassword", "")) if new_store else None
        manager_name = clean(fields.get("managerUsername"), 80)
        manager_password = str(fields.get("managerPassword", ""))
        confirm_password = str(fields.get("confirmPassword", ""))
        admin_key = str(fields.get("adminKey", ""))
        if not hmac.compare_digest(admin_key, self.admin_key):
            raise IdentityError("forbidden", "The admin key is incorrect.")
        if not store_code or not manager_name or (new_store and not store_name):
            message = "Store name, store code, and manager name are required." if new_store else "Store code and manager name are required."
            raise IdentityError("invalid", message)
        if new_store and (len(store_code) < 2 or len(crew_password) < 8):
            raise IdentityError("invalid", "Store code must be at least 2 characters and the crew password at least 8 characters.")
        if len(manager_name) < 2 or len(manager_password) < 8:
            raise IdentityError("invalid", "Manager name must be at least 2 characters and the manager password at least 8 characters.")
        if manager_password != confirm_password:
            raise IdentityError("invalid", "Manager passwords do not match.")
        store_id = None
        code_hash = hash_store_code(store_code) if new_store else None
        crew_hash = self.password_hasher(crew_password, f"shiftly-crew:{code_hash}") if new_store else None
        if not new_store:
            store = self.store_lookup(store_code)
            if not store:
                raise IdentityError("not_found", "That store could not be found.")
            store_id, store_name = store
        salt = self.token_factory(24)
        manager_hash = self.password_hasher(manager_password, salt)
        token = self.token_factory(32)
        try:
            self.repository.create_account(
                store_id=store_id, store_name=store_name, code_hash=code_hash, crew_hash=crew_hash,
                manager_name=manager_name, salt=salt, password_hash=manager_hash,
                token=token, ttl=self.session_ttl,
            )
        except psycopg.errors.UniqueViolation as error:
            message = "That store code or manager name is already in use." if new_store else "That manager name is already in use."
            raise IdentityError("conflict", message) from error
        return SessionResult("manager", token, {
            "authenticated": True, "role": "manager", "managerName": manager_name, "storeName": store_name,
        }, self.session_ttl)
