"""Single-process admission budgets; adapters supply a trusted peer address."""

import time
from threading import RLock

from .primitives import hash_store_code


class AdmissionControl:
    def __init__(self, *, clock=None, requests=None, failures=None, in_flight=None,
                 signups=None, lock=None, login_limit=10, login_window=900):
        self.clock = clock if clock is not None else time.time
        self.requests = requests if requests is not None else {}
        self.failures = failures if failures is not None else {}
        self.in_flight = in_flight if in_flight is not None else {}
        self.signups = signups if signups is not None else {}
        self.lock = lock if lock is not None else RLock()
        self.login_limit = login_limit
        self.login_window = login_window

    def login_key(self, client_key, store_code):
        return f"{client_key}:{hash_store_code(store_code)}"

    def _recent_failures(self, key):
        now = self.clock()
        recent = [stamp for stamp in self.failures.get(key, []) if now - stamp < self.login_window]
        self.failures[key] = recent
        return recent

    def login_limited(self, client_key, store_code):
        key = self.login_key(client_key, store_code)
        with self.lock:
            return len(self._recent_failures(key)) + self.in_flight.get(key, 0) >= self.login_limit

    def reserve_login(self, client_key, store_code):
        key = self.login_key(client_key, store_code)
        with self.lock:
            active = self.in_flight.get(key, 0)
            if len(self._recent_failures(key)) + active >= self.login_limit:
                return False
            self.in_flight[key] = active + 1
            return True

    def finish_login(self, client_key, store_code, *, failed):
        key = self.login_key(client_key, store_code)
        with self.lock:
            if failed:
                self.failures.setdefault(key, []).append(self.clock())
            remaining = self.in_flight[key] - 1
            if remaining:
                self.in_flight[key] = remaining
            else:
                del self.in_flight[key]

    def record_login_failure(self, client_key, store_code):
        with self.lock:
            self.failures.setdefault(self.login_key(client_key, store_code), []).append(self.clock())

    def report_limited(self, client_key):
        with self.lock:
            now = self.clock()
            recent = [stamp for stamp in self.requests.get(client_key, []) if now - stamp < 3600]
            self.requests[client_key] = recent
            if len(recent) >= 30:
                return True
            recent.append(now)
            return False

    def _recent_signups(self, client_key):
        now = self.clock()
        recent = [stamp for stamp in self.signups.get(client_key, []) if now - stamp < 3600]
        self.signups[client_key] = recent
        return recent

    def signup_limited(self, client_key):
        with self.lock:
            return len(self._recent_signups(client_key)) >= 5

    def record_signup(self, client_key):
        with self.lock:
            self.signups.setdefault(client_key, []).append(self.clock())

    def admit_signup(self, client_key):
        with self.lock:
            recent = self._recent_signups(client_key)
            if len(recent) >= 5:
                return False
            recent.append(self.clock())
            return True
