"""
Хендлер кнопок напоминания (✅ Выполнено / ❌ Не сделал / 📅 Перенести),
которые бот присылает под сообщением из app.scheduler.

Перенос — небольшой FSM-диалог (спросить новую дату, затем новое время),
т.к. в чате бота нет формы, как в WebApp.
"""

from datetime import date, datetime

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from app.database import session_scope
from app.logger import get_logger
from app.models import Achievement, TaskStatus
from app.services.achievement_service import check_and_award
from app.services.exceptions import TaskNotFoundError, TaskNotOwnedError
from app.services.task_service import get_owned_task, move_task, set_task_status
from app.services.user_service import get_or_create_user

router = Router(name="reminders")
logger = get_logger(__name__)


class MoveTaskStates(StatesGroup):
    waiting_date = State()
    waiting_time = State()


def _parse_task_id(callback_data: str) -> int:
    return int(callback_data.rsplit(":", 1)[-1])


async def _set_status_from_reminder(callback: CallbackQuery, status: TaskStatus, label: str) -> None:
    if callback.data is None or callback.from_user is None:
        return
    task_id = _parse_task_id(callback.data)
    tg_user = callback.from_user

    new_achievements: list[Achievement] = []
    async with session_scope() as session:
        user = await get_or_create_user(
            session, telegram_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name
        )
        try:
            task = await get_owned_task(session, user, task_id)
        except (TaskNotFoundError, TaskNotOwnedError):
            await callback.answer("Задача не найдена (возможно, уже удалена)", show_alert=True)
            return
        await set_task_status(session, task, status)
        new_achievements = await check_and_award(session, user)

    if isinstance(callback.message, Message):
        base_text = callback.message.text or ""
        await callback.message.edit_text(f"{base_text}\n\n{label}", reply_markup=None)
    await callback.answer(label)

    for achievement in new_achievements:
        if isinstance(callback.message, Message):
            await callback.message.answer(
                f"{achievement.icon} Новое достижение: «{achievement.title}»"
            )


@router.callback_query(F.data.startswith("reminder:done:"))
async def handle_reminder_done(callback: CallbackQuery) -> None:
    await _set_status_from_reminder(callback, TaskStatus.DONE, "✅ Отмечено как выполнено")


@router.callback_query(F.data.startswith("reminder:missed:"))
async def handle_reminder_missed(callback: CallbackQuery) -> None:
    await _set_status_from_reminder(callback, TaskStatus.MISSED, "❌ Отмечено как не выполнено")


@router.callback_query(F.data.startswith("reminder:move:"))
async def handle_reminder_move_start(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.data is None:
        return
    task_id = _parse_task_id(callback.data)
    await state.update_data(task_id=task_id)
    await state.set_state(MoveTaskStates.waiting_date)
    await callback.answer()
    if isinstance(callback.message, Message):
        await callback.message.answer(
            "📅 На какую дату перенести? Формат: ГГГГ-ММ-ДД (например, 2026-07-25)"
        )


@router.message(StateFilter(MoveTaskStates.waiting_date))
async def handle_move_date(message: Message, state: FSMContext) -> None:
    try:
        new_date = datetime.strptime((message.text or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        await message.answer("Не получилось распознать дату. Формат: ГГГГ-ММ-ДД (например, 2026-07-25)")
        return

    await state.update_data(new_date=new_date.isoformat())
    await state.set_state(MoveTaskStates.waiting_time)
    await message.answer("🕛 На какое время? Формат: ЧЧ:ММ (например, 09:00)")


@router.message(StateFilter(MoveTaskStates.waiting_time))
async def handle_move_time(message: Message, state: FSMContext) -> None:
    try:
        new_time = datetime.strptime((message.text or "").strip(), "%H:%M").time()
    except ValueError:
        await message.answer("Не получилось распознать время. Формат: ЧЧ:ММ (например, 09:00)")
        return

    data = await state.get_data()
    task_id: int = data["task_id"]
    new_date: date = date.fromisoformat(data["new_date"])
    tg_user = message.from_user
    await state.clear()

    if tg_user is None:
        return

    async with session_scope() as session:
        user = await get_or_create_user(
            session, telegram_id=tg_user.id, username=tg_user.username, first_name=tg_user.first_name
        )
        try:
            task = await get_owned_task(session, user, task_id)
        except (TaskNotFoundError, TaskNotOwnedError):
            await message.answer("Задача уже не найдена — возможно, была удалена.")
            return
        await move_task(session, task, new_date, new_time)
        title = task.title

    await message.answer(
        f"📅 Задача «{title}» перенесена на {new_date.strftime('%d.%m.%Y')} {new_time.strftime('%H:%M')}"
    )
    logger.info("Задача id=%s перенесена через напоминание на %s %s", task_id, new_date, new_time)
