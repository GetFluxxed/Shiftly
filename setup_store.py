#!/usr/bin/env python3
"""Create or reset a local Shiftly store and its first manager account."""

import argparse

import server
from security import hash_store_code, password_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-code", required=True)
    parser.add_argument("--crew-password", required=True)
    parser.add_argument("--manager", required=True)
    parser.add_argument("--manager-password", required=True)
    parser.add_argument("--store-name", default="Main Store")
    parser.add_argument("--reset", action="store_true", help="Delete existing reports, accounts, and sessions first.")
    args = parser.parse_args()

    server.initialize_database()
    code_hash = hash_store_code(args.store_code)
    crew_hash = password_hash(args.crew_password, f"shiftly-crew:{code_hash}")
    manager_salt = args.manager.casefold()
    manager_hash = password_hash(args.manager_password, manager_salt)

    with server.db_connection() as connection:
        with connection.cursor() as cursor:
            if args.reset:
                cursor.execute(
                    "TRUNCATE briefings, briefing_jobs, reports, manager_sessions, crew_sessions, "
                    "store_memberships, manager_users, stores RESTART IDENTITY CASCADE"
                )
            cursor.execute(
                "INSERT INTO stores (name, access_code_hash, crew_password_hash) "
                "VALUES (%s, %s, %s) RETURNING id",
                (args.store_name, code_hash, crew_hash),
            )
            store_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO manager_users (username, email, password_salt, password_hash) "
                "VALUES (%s, NULL, %s, %s) RETURNING id",
                (args.manager, manager_salt, manager_hash),
            )
            manager_id = cursor.fetchone()[0]
            cursor.execute(
                "INSERT INTO store_memberships (manager_user_id, store_id, role) "
                "VALUES (%s, %s, 'manager')",
                (manager_id, store_id),
            )
        connection.commit()
    print(f"Configured {args.store_name} ({args.store_code}) with manager {args.manager}.")


if __name__ == "__main__":
    main()
