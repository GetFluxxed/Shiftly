"""Initialize one empty, loopback-only developer database; never reads .env.

This operator command is not registered with either HTTP adapter. It creates no
catalog, recipes or stock, and refuses any existing workspace or account.
"""

import argparse
import getpass
import os
import secrets
import sys
import warnings

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from backend.shiftly.identity.accounts_core import policy_lock
from backend.shiftly.identity.primitives import hash_store_code, password_hash
from .migrate import require_schema


DEMO_USERNAME = 'demo-owner'


def demo_connection_string(value):
    """Explicit local targets only; no service files or ambient application URL."""
    if not value:
        raise ValueError('DEMO_DATABASE_URL is required.')
    try:
        fields = conninfo_to_dict(value)
    except psycopg.Error:
        raise ValueError('DEMO_DATABASE_URL is invalid.') from None
    if set(fields) - {'host', 'port', 'dbname', 'user', 'password', 'sslmode'}:
        raise ValueError('Demo connections require explicit ordinary connection fields.')
    if fields.get('host') not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('The demo database must use a loopback host.')
    if not fields.get('dbname', '').startswith('shiftly_demo_'):
        raise ValueError('The database name must start with shiftly_demo_.')
    if not fields.get('port') or not fields.get('user'):
        raise ValueError('An explicit database port and user are required.')
    return make_conninfo(**fields, connect_timeout=5)


def create_demo_workspace(connect, password):
    if not isinstance(password, str) or not 8 <= len(password) <= 1024:
        raise ValueError('Choose a password containing 8 to 1024 characters.')
    require_schema(connect)
    salt = secrets.token_urlsafe(24)
    with connect() as connection:
        policy_lock(connection)
        for table in ('businesses', 'stores', 'account_users', 'manager_users'):
            if connection.execute(f'SELECT 1 FROM {table} LIMIT 1').fetchone():
                raise ValueError('This database already contains a workspace or account; nothing was changed.')
        business_id = connection.execute(
            "INSERT INTO businesses(name) VALUES('Demo Company') RETURNING id"
        ).fetchone()[0]
        store_id = connection.execute(
            """INSERT INTO stores(name, access_code_hash, business_id,
                                  accounts_enabled, shared_crew_enabled)
               VALUES('Demo Store', %s, %s, true, false) RETURNING id""",
            (hash_store_code(secrets.token_urlsafe(24)), business_id),
        ).fetchone()[0]
        user_id = connection.execute(
            """INSERT INTO account_users(username, display_name, password_salt, password_hash)
               VALUES(%s, 'Demo Owner', %s, %s) RETURNING id""",
            (DEMO_USERNAME, salt, password_hash(password, salt)),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO business_memberships(user_id, business_id, role) VALUES(%s, %s, 'owner')",
            (user_id, business_id),
        )
        connection.execute(
            """INSERT INTO account_audit(subject_user_id, business_id, store_id, action, reason)
               VALUES(%s, %s, %s, 'demo.workspace_initialized', 'Explicit local empty-database initialization')""",
            (user_id, business_id, store_id),
        )
        connection.commit()
    return {'username': DEMO_USERNAME, 'storeId': store_id}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--create-empty-workspace', action='store_true', required=True,
                        help='Create a local demo owner and store only if no workspace exists.')
    parser.parse_args(argv)
    try:
        dsn = demo_connection_string(os.environ.get('DEMO_DATABASE_URL', ''))
        if not sys.stdin.isatty():
            raise ValueError('Demo setup requires an interactive terminal with hidden password input.')
        with warnings.catch_warnings():
            warnings.simplefilter('error', getpass.GetPassWarning)
            password = getpass.getpass('New demo-owner password: ')
            if password != getpass.getpass('Confirm password: '):
                raise ValueError('Passwords did not match.')
        create_demo_workspace(lambda: psycopg.connect(dsn), password)
    except getpass.GetPassWarning:
        raise SystemExit('Secure password input is unavailable; use an interactive terminal.') from None
    except (ValueError, RuntimeError) as error:
        raise SystemExit(str(error)) from None
    except (psycopg.Error, EOFError, KeyboardInterrupt):
        raise SystemExit('Demo initialization did not complete. Check the local database and current schema.') from None
    print('Demo workspace created. Sign in as demo-owner using the password you entered.')


if __name__ == '__main__':
    main()
