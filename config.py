import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    host: str = "127.0.0.1"
    port: int = 4173
    secure_cookies: bool = False
    database_url: str = ""
    admin_signup_key: str = ""
    openai_model: str = "gpt-4o-mini"
    report_cooldown_seconds: int = 60
    openai_api_key: str = ""
    db_pool_max_size: int = 4
    db_pool_timeout: float = 3.0
    db_connect_timeout: int = 5
    db_statement_timeout_ms: int = 10000
    db_lock_timeout_ms: int = 2000
    db_idle_transaction_timeout_ms: int = 30000
    shutdown_timeout: float = 5.0
    worker_stale_seconds: float = 60.0
    worker_mode: str = "embedded"
    web_concurrency: int = 1


def load_env_file(env_path: str | None = None):
    path = env_path or os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.isfile(path):
        return
    for raw_line in open(path, encoding="utf-8"):
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")
        if key and key not in os.environ:
            os.environ[key] = value


def load_settings(*, load_env=True) -> Settings:
    if load_env:
        load_env_file()
    return Settings(
        host=os.environ.get("HOST", "127.0.0.1").strip() or "127.0.0.1",
        port=int(os.environ.get("PORT", "4173")),
        secure_cookies=os.environ.get("SECURE_COOKIES", "false").strip().casefold() in {"1", "true", "yes", "on"},
        database_url=os.environ.get("DATABASE_URL", "").strip(),
        admin_signup_key=os.environ.get("ADMIN_SIGNUP_KEY", "").strip(),
        openai_model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        report_cooldown_seconds=int(os.environ.get("REPORT_COOLDOWN_SECONDS", "60")),
        openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
        db_pool_max_size=int(os.environ.get("DB_POOL_MAX_SIZE", "4")),
        db_pool_timeout=float(os.environ.get("DB_POOL_TIMEOUT", "3")),
        db_connect_timeout=int(os.environ.get("DB_CONNECT_TIMEOUT", "5")),
        db_statement_timeout_ms=int(os.environ.get("DB_STATEMENT_TIMEOUT_MS", "10000")),
        db_lock_timeout_ms=int(os.environ.get("DB_LOCK_TIMEOUT_MS", "2000")),
        db_idle_transaction_timeout_ms=int(os.environ.get("DB_IDLE_TRANSACTION_TIMEOUT_MS", "30000")),
        shutdown_timeout=float(os.environ.get("SHUTDOWN_TIMEOUT", "5")),
        worker_stale_seconds=float(os.environ.get("WORKER_STALE_SECONDS", "60")),
        worker_mode=os.environ.get("SHIFTLY_WORKER_MODE", "embedded").strip(),
        web_concurrency=int(os.environ.get("WEB_CONCURRENCY", "1")),
    )
