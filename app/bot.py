"""Точка входа для запуска Telegram-бота (long polling)."""

import asyncio

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import init_db
from app.handlers import get_main_router
from app.logger import get_logger, setup_logging
from app.scheduler import create_scheduler

logger = get_logger(__name__)


async def main() -> None:
    setup_logging()
    logger.info("Запуск бота...")

    await init_db()

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    # MemoryStorage хватает для одного процесса (FSM переноса задачи через
    # напоминание). При масштабировании на несколько процессов потребуется
    # RedisStorage — архитектура aiogram это позволяет без изменения хендлеров.
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


if __name__ == "__main__":
    asyncio.run(main())
