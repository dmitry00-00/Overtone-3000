"""Конфигурация из окружения. Без токена бота включается dev-авторизация по заголовку.

Значения читаются при создании Settings(), а не при импорте: .env загружается раньше.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _dsn() -> str:
    """OKNO_DSN, иначе DATABASE_URL хостинга (postgres:// нормализуется), иначе локальная база."""
    dsn = _env("OKNO_DSN") or _env("DATABASE_URL") or "postgresql://localhost/okno"
    return "postgresql://" + dsn.removeprefix("postgres://") if dsn.startswith("postgres://") else dsn


@dataclass(frozen=True)
class Settings:
    dsn: str = field(default_factory=_dsn)
    bot_token: str | None = field(default_factory=lambda: _env("OKNO_BOT_TOKEN") or None)
    dev_auth: bool = field(default_factory=lambda: _env("OKNO_DEV_AUTH") == "1")
    tick_interval_s: float = field(default_factory=lambda: float(_env("OKNO_TICK_INTERVAL", "30")))
    initdata_max_age_s: int = field(default_factory=lambda: int(_env("OKNO_INITDATA_MAX_AGE", "86400")))
    webapp_url: str | None = field(default_factory=lambda: _env("OKNO_WEBAPP_URL") or None)  # https-адрес Mini App
    app_short_name: str | None = field(default_factory=lambda: _env("OKNO_APP_SHORT_NAME") or None)  # из /newapp
    run_bot: bool = field(default_factory=lambda: _env("OKNO_RUN_BOT", "1") == "1")

    def __post_init__(self) -> None:
        if not self.bot_token and not self.dev_auth:
            raise RuntimeError("нужен OKNO_BOT_TOKEN или OKNO_DEV_AUTH=1")
