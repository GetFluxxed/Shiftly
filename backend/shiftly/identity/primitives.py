"""Value-only credential and text helpers shared by both transports."""

import hashlib
import re


def clean(value, limit):
    return re.sub(r"\s+", " ", value or "").strip()[:limit]


def password_hash(password, salt):
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 240000).hex()


def hash_store_code(store_code):
    return hashlib.sha256(store_code.casefold().encode()).hexdigest()


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()
