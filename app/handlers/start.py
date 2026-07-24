"""Хендлер команды /start."""

from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import KeyboardButton, Message, ReplyKeyboardMarkup, WebAppInfo

from app.config import settings
from app.database import session_scope
from app.logger import get_logger
from app.services.user_service import get_or_create_user

router = Router(name="start")
logger = get_logger(__name__)

WELCOME_TEXT = (
    "👋 Привет, {name}!\n\n"
    "Это трекер привычек и распорядка дня.\n"
    "Открой WebApp кнопкой ниже, чтобы посмотреть календарь и задачи."
)


def _webapp_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📅 Открыть трекер", web_app=WebAppInfo(url=settings.webapp_url))]],
        resize_keyboard=True,
    )


@router.message(CommandStart())
async def handle_start(message: Message) -> None:
    tg_user = message.from_user
    if tg_user is None:
        return

    async with session_scope() as session:
        user = await get_or_create_user(
            session,
            telegram_id=tg_user.id,
            username=tg_user.username,
            first_name=tg_user.first_name,
        )
        name = user.first_name or "друг"

    await message.answer(WELCOME_TEXT.format(name=name), reply_markup=_webapp_keyboard())
    logger.info("Обработана команда /start от telegram_id=%s", tg_user.id)
