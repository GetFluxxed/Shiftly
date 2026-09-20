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


def load_settings() -> Settings:
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
    )
