"""
Статистика для страницы «История»: показатели за период (Сегодня/Неделя/
Месяц/Всё время), серии полностью выполненных дней (текущая и лучшая),
самый продуктивный день, последние выполненные/пропущенные задачи.

Источник истины по текущему статусу задачи — сама модель Task (как и в
календаре), а не TaskHistory: если пользователь несколько раз менял статус
задачи туда-сюда, в статистике должен учитываться только финальный результат,
а не каждое промежуточное нажатие. TaskHistory в проекте остаётся логом
событий на будущее (например, для более тонкой аналитики), но не требуется
для показателей этого этапа.
"""

from datetime import date, datetime, timedelta
from typing import Literal, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.logger import get_logger
from app.models import Task, TaskStatus, User
from app.services.task_service import (
    DAY_STATE_DONE,
    DAY_STATE_OVERDUE,
    classify_day_states,
    list_tasks_for_period,
)

logger = get_logger(__name__)

Period = Literal["today", "week", "month", "all"]

# Достаточно далёкая нижняя граница для периода "Всё время" — заведомо раньше
# появления первой задачи у любого пользователя. Не расширяет генерацию
# экземпляров серий (та ограничена верхней границей диапазона), только
# фильтрует уже существующие строки Task, поэтому лишней нагрузки не создаёт.
ALL_TIME_START = date(2020, 1, 1)


class MostProductiveDay(TypedDict):
    date: date
    done_count: int


class HistoryStats(TypedDict):
    period: Period
    start: date
    end: date
    done_count: int
    missed_count: int
    percent: int
    current_streak: int
    best_streak: int
    most_productive_day: MostProductiveDay | None
    recent_done: list[Task]
    recent_missed: list[Task]


def period_range(period: Period, today: date) -> tuple[date, date]:
    if period == "today":
        return today, today
    if period == "week":
        return today - timedelta(days=6), today
    if period == "month":
        return today - timedelta(days=29), today
    return ALL_TIME_START, today


def _most_productive_day(tasks: list[Task], start: date, end: date) -> MostProductiveDay | None:
    counts: dict[date, int] = {}
    for t in tasks:
        if start <= t.task_date <= end and t.status == TaskStatus.DONE:
            counts[t.task_date] = counts.get(t.task_date, 0) + 1
    if not counts:
        return None
    best_day = max(counts, key=lambda d: counts[d])
    return MostProductiveDay(date=best_day, done_count=counts[best_day])


def compute_streaks(day_states: dict[date, str], today: date) -> tuple[int, int]:
    """
    Серия считается по дням, в которые вообще были задачи — день без единой
    задачи не засчитывается и не обрывает серию (в трекере привычек не каждый
    день обязан что-то планировать).

    Публична, т.к. переиспользуется в app.services.achievement_service для
    правил "N дней подряд" — там нужна ровно та же логика серии, что и в
    статистике, без второй реализации.

    Лучшая серия — максимальный такой пробег за всё время.
    Текущая серия — пробег полностью выполненных дней назад от сегодня.
    Сегодняшний день, если он ещё не завершён (есть невыполненные-непросроченные
    задачи), не засчитывается в серию, но и не обрывает её — день просто ещё
    не закончился. Обрывает серию только явный "просрочен" (🔴).
    """
    days_with_tasks = sorted(day_states.keys())
    if not days_with_tasks:
        return 0, 0

    best = 0
    running = 0
    for day in days_with_tasks:
        if day_states[day] == DAY_STATE_DONE:
            running += 1
            best = max(best, running)
        else:
            running = 0

    current = 0
    if today in day_states:
        if day_states[today] == DAY_STATE_DONE:
            current += 1
        elif day_states[today] == DAY_STATE_OVERDUE:
            return current, best  # серия оборвана прямо сегодня

    day = today - timedelta(days=1)
    earliest = days_with_tasks[0]
    while day >= earliest:
        state = day_states.get(day)
        if state is None:
            day -= timedelta(days=1)
            continue
        if state == DAY_STATE_DONE:
            current += 1
            day -= timedelta(days=1)
        else:
            break

    return current, best


async def get_history(session: AsyncSession, user: User, period: Period) -> HistoryStats:
    today = date.today()
    start, end = period_range(period, today)

    # Одним запросом берём все задачи пользователя вплоть до сегодня — этого
    # достаточно и для серий (всегда всё время), и для показателей периода
    # (фильтруются в Python из того же набора, без второго похода в БД).
    all_tasks = await list_tasks_for_period(session, user, ALL_TIME_START, today)

    day_states = classify_day_states(all_tasks, today)
    current_streak, best_streak = compute_streaks(day_states, today)

    period_tasks = [t for t in all_tasks if start <= t.task_date <= end]
    done_count = sum(1 for t in period_tasks if t.status == TaskStatus.DONE)
    missed_count = sum(1 for t in period_tasks if t.status == TaskStatus.MISSED)
    resolved = done_count + missed_count
    percent = round(done_count / resolved * 100) if resolved else 0

    most_productive = _most_productive_day(all_tasks, start, end)

    recent_done = sorted(
        (t for t in period_tasks if t.status == TaskStatus.DONE),
        key=lambda t: t.completed_at or datetime.min,
        reverse=True,
    )[:5]
    # У Task нет отдельной отметки времени "когда помечен пропущенным" —
    # используем дату задачи как естественный порядок для этого списка.
    recent_missed = sorted(
        (t for t in period_tasks if t.status == TaskStatus.MISSED),
        key=lambda t: (t.task_date, t.task_time),
        reverse=True,
    )[:5]

    logger.info(
        "Статистика (period=%s) для user_id=%s: done=%s missed=%s streak=%s/%s",
        period, user.id, done_count, missed_count, current_streak, best_streak,
    )

    return HistoryStats(
        period=period,
        start=start,
        end=end,
        done_count=done_count,
        missed_count=missed_count,
        percent=percent,
        current_streak=current_streak,
        best_streak=best_streak,
        most_productive_day=most_productive,
        recent_done=recent_done,
        recent_missed=recent_missed,
    )
