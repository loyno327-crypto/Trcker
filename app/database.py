"""
Настройка подключения к базе данных через SQLAlchemy (async).

Архитектура намеренно не завязана на SQLite: вся работа идёт через
async engine и async-сессии SQLAlchemy, поэтому переход на PostgreSQL
(например, с asyncpg) потребует только смены DATABASE_URL в .env.
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


class Base(DeclarativeBase):
    """Базовый класс для всех ORM-моделей проекта."""


engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def init_db() -> None:
    """Создаёт таблицы, если их ещё нет, и досеивает каталог достижений.
    Вызывается один раз при старте."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("База данных инициализирована (%s)", settings.database_url)
    await seed_achievements()


async def seed_achievements() -> None:
    """
    Заполняет таблицу achievements из app.services.achievement_service.ACHIEVEMENT_CATALOG.

    Идемпотентно и безопасно на каждом старте: уже существующие по `code`
    записи не трогает (и не перезаписывает их title/description/icon, если
    их вручную поменяли в БД), добавляет только те коды каталога, которых в
    таблице ещё нет. Так в будущем можно дописать новое достижение только в
    ACHIEVEMENT_CATALOG — оно появится в БД при следующем запуске, без
    миграций и без потери уже полученных пользователями UserAchievement.
    """
    # Импорт внутри функции, а не на верхнем уровне модуля — иначе
    # circular import (achievement_service -> task_service -> ... -> database).
    from app.models import Achievement
    from app.services.achievement_service import ACHIEVEMENT_CATALOG

    async with async_session_factory() as session:
        result = await session.execute(select(Achievement.code))
        existing_codes = set(result.scalars().all())

        added = 0
        for definition in ACHIEVEMENT_CATALOG:
            if definition.code in existing_codes:
                continue
            session.add(
                Achievement(
                    code=definition.code,
                    title=definition.title,
                    description=definition.description,
                    icon=definition.icon,
                )
            )
            added += 1

        if added:
            await session.commit()
            logger.info("Досеяно %d новых достижений в каталог", added)


@asynccontextmanager
async def session_scope() -> AsyncGenerator[AsyncSession, None]:
    """
    Контекстный менеджер для использования в сервисах/хендлерах бота:

        async with session_scope() as session:
            ...

    Коммитит при успехе, откатывает при исключении, всегда закрывает сессию.
    """
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI-зависимость (Depends(get_session)) для веб-части.

    Коммитит при успешном ответе: некоторые GET-эндпоинты как побочный эффект
    дозаписывают данные (например, генерируют экземпляры задач на новый
    диапазон дат или регистрируют пользователя при первом обращении), и эти
    изменения должны сохраняться.
    """
    session = async_session_factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()
