from aiogram import Router

from app.handlers.reminders import router as reminders_router
from app.handlers.start import router as start_router


def get_main_router() -> Router:
    """Собирает все роутеры бота в один. Новые хендлеры подключаются здесь."""
    router = Router(name="main")
    router.include_router(start_router)
    router.include_router(reminders_router)
    return router
