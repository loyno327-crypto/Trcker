"""
Планировщик напоминаний (APScheduler).

Раз в `settings.reminder_check_interval_seconds` проверяет задачи, время
которых уже наступило и по которым ещё не отправлено напоминание
(`Task.reminder_sent`), и шлёт в бот сообщение с кнопками
✅ Выполнено / ❌ Не сделал / 📅 Перенести. Нажатие обрабатывается в
`app.handlers.reminders`.

Логика не привязана к тому, что задача "на сегодня" — если процесс не
работал какое-то время, просроченные задачи из прошлого тоже получат
напоминание при следующей проверке (наверстывание пропущенных).
"""

from datetime import datetime

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import session_scope
from app.logger import get_logger
from app.models import Task, TaskStatus

logger = get_logger(__name__)

REMINDER_TEXT = "🔔 Напоминание\nБыла задача:\n{title}\n🕛 {time}"


def _reminder_keyboard(task_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ Выполнено", callback_data=f"reminder:done:{task_id}"),
                InlineKeyboardButton(text="❌ Не сделал", callback_data=f"reminder:missed:{task_id}"),
                InlineKeyboardButton(text="📅 Перенести", callback_data=f"reminder:move:{task_id}"),
            ]
        ]
    )


async def _fetch_due_tasks(session) -> list[Task]:
    """Задачи, чьё время (task_date + task_time) уже наступило и по которым
    ещё не отправлено напоминание. Отбор по дате делается в SQL, финальная
    сверка по времени — в Python (SQLite не умеет сравнивать Date+Time одним
    выражением так же просто, как Python)."""
    now = datetime.now()
    result = await session.execute(
        select(Task)
        .where(
            Task.status == TaskStatus.PENDING,
            Task.reminder_sent.is_(False),
            Task.task_date <= now.date(),
        )
        .options(selectinload(Task.user))
    )
    candidates = result.scalars().all()
    return [t for t in candidates if datetime.combine(t.task_date, t.task_time) <= now]


async def check_and_send_reminders(bot: Bot) -> None:
    async with session_scope() as session:
        due_tasks = await _fetch_due_tasks(session)
        for task in due_tasks:
            try:
                await bot.send_message(
                    chat_id=task.user.telegram_id,
                    text=REMINDER_TEXT.format(title=task.title, time=task.task_time.strftime("%H:%M")),
                    reply_markup=_reminder_keyboard(task.id),
                )
                task.reminder_sent = True
                logger.info("Отправлено напоминание по задаче id=%s telegram_id=%s", task.id, task.user.telegram_id)
            except TelegramAPIError as exc:
                # Например, пользователь заблокировал бота — не роняем весь цикл проверки.
                logger.warning("Не удалось отправить напоминание по задаче id=%s: %s", task.id, exc)


def create_scheduler(bot: Bot) -> AsyncIOScheduler:
    """Создаёт (но не запускает) планировщик с job'ой проверки напоминаний.
    Вызывающий код должен вызвать .start() и, на завершении, .shutdown()."""
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        trigger="interval",
        seconds=settings.reminder_check_interval_seconds,
        args=[bot],
        id="reminder_check",
        max_instances=1,
        coalesce=True,
        misfire_grace_time=None,
    )
    return scheduler
