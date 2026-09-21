import os

import psycopg


def db_connection():
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if psycopg is None:
        raise RuntimeError("psycopg is not installed. Run: python3 -m pip install -r requirements.txt")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not configured.")
    from config import load_settings
    from backend.shiftly.runtime.database import connect_dedicated
    # Keep the existing factory's environment lookup and dedicated-close contract.
    return connect_dedicated(load_settings(load_env=False))
