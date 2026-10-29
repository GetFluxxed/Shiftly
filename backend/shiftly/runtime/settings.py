"""Validation for the initial one-API-process runtime."""

import math


def validate_runtime_settings(settings):
    if settings.web_concurrency != 1:
        raise ValueError("Only one API process is supported; shared admission is required before scale-out.")
    if settings.worker_mode not in {"embedded", "external"}:
        raise ValueError("SHIFTLY_WORKER_MODE must be embedded or external.")
    for name in ("db_pool_max_size", "db_pool_timeout", "db_connect_timeout",
                 "db_statement_timeout_ms", "db_lock_timeout_ms", "db_idle_transaction_timeout_ms",
                 "shutdown_timeout", "worker_stale_seconds"):
        value = getattr(settings, name)
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be a finite positive number.")
    if settings.db_pool_max_size < 1:
        raise ValueError("db_pool_max_size must be at least one.")
