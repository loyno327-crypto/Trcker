"""
Единая точка входа для хостингов ботов (например, BotHost), которые
запускают один процесс из одного файла в корне проекта.

Поднимает в одном asyncio event loop:
- Telegram-бота (aiogram, long polling);
- FastAPI-сервер (REST API для WebApp + раздача его статики).

Локально для разработки по-прежнему можно (и удобнее) запускать раздельно:

    python -m app.bot                                  — только бот
    uvicorn app.web.main:app --reload --port 8000       — только веб-часть

Этот файл ничего не дублирует — он просто одновременно запускает те же
функции/приложение, что и `app/bot.py` и `app/web/main.py`.
"""

import asyncio
import os

import uvicorn
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import init_db
from app.handlers import get_main_router
from app.logger import get_logger, setup_logging
from app.scheduler import create_scheduler
from app.web.main import app as fastapi_app

logger = get_logger(__name__)


async def run_bot() -> None:
    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(get_main_router())

    scheduler = create_scheduler(bot)
    scheduler.start()
    logger.info(
        "Планировщик напоминаний запущен (интервал %sс)", settings.reminder_check_interval_seconds
    )

    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Бот запущен, начинаю polling")
    try:
        await dispatcher.start_polling(bot)
    finally:
        scheduler.shutdown(wait=False)


async def run_web() -> None:
    # Многие хостинги ботов (в т.ч. BotHost) сами назначают порт через
    # переменную окружения PORT и ждут, что процесс слушает именно его —
    # если она задана, она в приоритете над WEB_PORT из .env.
    port = int(os.environ.get("PORT", settings.web_port))

    config = uvicorn.Config(
        fastapi_app,
        host=settings.web_host,
        port=port,
        log_level=settings.log_level.lower(),
        lifespan="on",
    )
    server = uvicorn.Server(config)
    logger.info("Веб-сервер запущен на %s:%s", settings.web_host, port)
    await server.serve()


async def main() -> None:
    setup_logging()
    await init_db()
    # Бот и веб-сервер работают параллельно в одном процессе; если один из
    # них падает с исключением, второй тоже останавливается — процесс должен
    # быть перезапущен целиком (это и делает хостинг при падении процесса).
    await asyncio.gather(run_bot(), run_web())


if __name__ == "__main__":
    asyncio.run(main())
