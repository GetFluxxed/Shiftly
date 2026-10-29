"""Explicit coordinated migration command: python -m backend.shiftly.runtime.migrate."""

from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parents[3] / "migrations"


def migrate(connection_factory, *, directory=MIGRATIONS, lock_timeout_ms=2000):
    if lock_timeout_ms <= 0:
        raise ValueError("Migration lock timeout must be positive.")
    applied = []
    with connection_factory() as connection:
        with connection.transaction():
            connection.execute("SELECT set_config('lock_timeout', %s, true)", (str(lock_timeout_ms),))
            # Schema-scoped for isolated tests; held until the whole upgrade commits.
            connection.execute("SELECT pg_advisory_xact_lock(hashtext(current_database()), hashtext(current_schema() || ':shiftly-migrate'))")
            connection.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW())")
            for migration in sorted(Path(directory).glob("*.sql")):
                if connection.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (migration.name,)).fetchone():
                    continue
                connection.execute(migration.read_text(encoding="utf-8"))
                connection.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (migration.name,))
                applied.append(migration.name)
        connection.commit()
    return applied


def schema_status(connection_factory, *, directory=MIGRATIONS):
    expected = {path.name for path in Path(directory).glob("*.sql")}
    try:
        with connection_factory() as connection:
            installed = {row[0] for row in connection.execute("SELECT version FROM schema_migrations").fetchall()}
    except (RuntimeError, psycopg.Error):
        return {"status": "degraded", "schemaReady": False, "pendingMigrations": sorted(expected)}
    pending = sorted(expected - installed)
    return {"status": "degraded" if pending else "ok", "schemaReady": not pending, "pendingMigrations": pending}


def require_schema(connection_factory):
    if not schema_status(connection_factory)["schemaReady"]:
        raise RuntimeError("Database schema is not ready; run the coordinated migration command first.")


def main():
    from config import load_settings
    from .database import connect_dedicated
    from .settings import validate_runtime_settings
    try:
        settings = load_settings(load_env=False)
        validate_runtime_settings(settings)
        applied = migrate(lambda: connect_dedicated(settings), lock_timeout_ms=settings.db_lock_timeout_ms)
    except (RuntimeError, ValueError, psycopg.Error):
        raise SystemExit("Migration failed; check configuration, database access and migration compatibility.") from None
    print(f"Migrations ready; applied {len(applied)} migration(s).")


if __name__ == "__main__":
    main()
