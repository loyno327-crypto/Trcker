"""
Центральная конфигурация проекта.

Все настройки читаются из переменных окружения (.env) через pydantic-settings.
Ничего в проекте не должно хардкодить токены/URL — только через объект `settings`.
"""

import os
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Telegram
    bot_token: str
    # Некоторые хостинги (например, BotHost) не пробрасывают в контейнер
    # переменную WEBAPP_URL, даже если она задана в панели, но всегда
    # предоставляют системную переменную DOMAIN. Поэтому webapp_url
    # необязателен, а если он не задан — собираем адрес из DOMAIN.
    webapp_url: str = ""

    # База данных.
    # По умолчанию SQLite, но URL в формате SQLAlchemy — переход на
    # PostgreSQL сводится к замене строки подключения
    # (например: postgresql+asyncpg://user:pass@host/db) без изменения кода.
    database_url: str = "sqlite+aiosqlite:///./habit_tracker.db"

    # Веб-сервер (FastAPI отдаёт WebApp и REST API для него)
    web_host: str = "0.0.0.0"
    web_port: int = 8000

    # Планировщик напоминаний
    reminder_check_interval_seconds: int = 60

    # На сколько дней вперёд заранее генерировать экземпляры повторяющихся задач
    task_generation_horizon_days: int = 60

    # Логирование
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Настройки читаются один раз и кэшируются на всё время работы процесса."""
    result = Settings()

    if not result.webapp_url:
        domain = os.environ.get("DOMAIN")
        if domain:
            result.webapp_url = f"https://{domain}"
        else:
            raise RuntimeError(
                "webapp_url не задан и не может быть выведен: "
                "нет ни переменной WEBAPP_URL, ни DOMAIN в окружении."
            )

    return result


settings = get_settings()
