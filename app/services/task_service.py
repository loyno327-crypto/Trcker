"""
Сервис для работы с задачами.

Отвечает за:
- создание задачи (разовой или серии повторений) и генерацию экземпляров;
- получение списка задач на дату (уже отсортированного);
- редактирование/перенос/удаление — с поддержкой "только эта задача" или
  "вся серия";
- отметку статуса выполнения и запись в историю.

Хендлеры бота и веб-API (следующие этапы) работают с задачами только через
этот модуль — прямых запросов к Task/TaskSeries вне сервисов быть не должно.
"""

from datetime import date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.logger import get_logger
from app.models import RepeatType, Task, TaskHistory, TaskSeries, TaskStatus, User
from app.services.exceptions import TaskNotFoundError, TaskNotOwnedError
from app.services.recurrence import dates_for_series

logger = get_logger(__name__)


async def ensure_series_generated(session: AsyncSession, series: TaskSeries, until_date: date) -> None:
    """Догенерировать экземпляры задач серии вплоть до until_date включительно."""
    range_from = series.last_generated_until + timedelta(days=1) if series.last_generated_until else series.start_date
    if range_from > until_date:
        return

    occurrence_dates = dates_for_series(series.repeat_type, series.start_date, range_from, until_date)
    for occurrence_date in occurrence_dates:
        session.add(
            Task(
                user_id=series.user_id,
                series_id=series.id,
                title=series.title,
                task_date=occurrence_date,
                task_time=series.time,
                status=TaskStatus.PENDING,
            )
        )

    series.last_generated_until = until_date
    await session.flush()
    if occurrence_dates:
        logger.info(
            "Сгенерировано %d экземпляров для серии id=%s (%s .. %s)",
            len(occurrence_dates),
            series.id,
            occurrence_dates[0],
            occurrence_dates[-1],
        )


async def create_task(
    session: AsyncSession,
    user: User,
    title: str,
    task_date: date,
    task_time: time,
    repeat_type: RepeatType = RepeatType.ONCE,
) -> Task:
    """Создаёт серию (даже для разовой задачи — repeat_type=ONCE) и её экземпляры."""
    series = TaskSeries(
        user_id=user.id,
        title=title.strip(),
        repeat_type=repeat_type,
        start_date=task_date,
        time=task_time,
    )
    session.add(series)
    await session.flush()

    horizon = task_date + timedelta(days=settings.task_generation_horizon_days)
    await ensure_series_generated(session, series, horizon)

    result = await session.execute(
        select(Task).where(Task.series_id == series.id, Task.task_date == task_date)
    )
    task = result.scalar_one()
    logger.info("Создана задача id=%s title=%r date=%s repeat=%s", task.id, title, task_date, repeat_type)
    return task


async def get_owned_task(session: AsyncSession, user: User, task_id: int) -> Task:
    result = await session.execute(
        select(Task).where(Task.id == task_id).options(selectinload(Task.series))
    )
    task = result.scalar_one_or_none()
    if task is None:
        raise TaskNotFoundError(f"Задача id={task_id} не найдена")
    if task.user_id != user.id:
        raise TaskNotOwnedError(f"Задача id={task_id} принадлежит другому пользователю")
    return task


async def list_tasks_for_date(session: AsyncSession, user: User, target_date: date) -> list[Task]:
    """Задачи на дату, отсортированные по времени, затем по времени создания."""
    await _ensure_generated_for_range(session, user, target_date)
    result = await session.execute(
        select(Task)
        .where(Task.user_id == user.id, Task.task_date == target_date)
        .order_by(Task.task_time, Task.created_at)
        .options(selectinload(Task.series))
    )
    return list(result.scalars().all())


async def update_task(
    session: AsyncSession,
    task: Task,
    *,
    scope: str,
    title: str | None = None,
    task_date: date | None = None,
    task_time: time | None = None,
    repeat_type: RepeatType | None = None,
) -> Task:
    """
    scope="this"   — меняет только этот экземпляр (title/task_date/task_time).
                      repeat_type для одного экземпляра не применим и игнорируется.
    scope="series" — меняет шаблон серии и распространяет title/time на все
                      ещё не выполненные и не наступившие задачи серии.
                      Дата (task_date) при scope="series" не меняется -
                      для переноса конкретной даты используйте move_task().
    """
    if scope == "this":
        if title is not None:
            task.title = title.strip()
        if task_date is not None:
            task.task_date = task_date
        if task_time is not None:
            task.task_time = task_time
        await session.flush()
        logger.info("Обновлена задача id=%s (scope=this)", task.id)
        return task

    if scope == "series":
        if task.series_id is None:
            # Разовая задача без серии — редактирование серии эквивалентно "this"
            return await update_task(
                session, task, scope="this", title=title, task_date=task_date, task_time=task_time
            )

        series_result = await session.execute(select(TaskSeries).where(TaskSeries.id == task.series_id))
        series = series_result.scalar_one()

        if title is not None:
            series.title = title.strip()
        if task_time is not None:
            series.time = task_time
        if repeat_type is not None:
            series.repeat_type = repeat_type

        pending_result = await session.execute(
            select(Task).where(
                Task.series_id == series.id,
                Task.status == TaskStatus.PENDING,
                Task.task_date >= date.today(),
            )
        )
        for pending_task in pending_result.scalars().all():
            if title is not None:
                pending_task.title = series.title
            if task_time is not None:
                pending_task.task_time = series.time

        await session.flush()
        logger.info("Обновлена серия id=%s (scope=series)", series.id)
        return task

    raise ValueError(f"Некорректный scope: {scope!r}, ожидается 'this' или 'series'")


async def move_task(session: AsyncSession, task: Task, new_date: date, new_time: time) -> Task:
    """Перенос задачи — всегда влияет только на конкретный экземпляр, не на серию."""
    return await update_task(session, task, scope="this", task_date=new_date, task_time=new_time)


async def delete_task(session: AsyncSession, task: Task, *, scope: str) -> None:
    if scope == "this":
        logger.info("Удалена задача id=%s (scope=this)", task.id)
        await session.delete(task)
        await session.flush()
        return

    if scope == "series":
        if task.series_id is None:
            await delete_task(session, task, scope="this")
            return

        series_result = await session.execute(select(TaskSeries).where(TaskSeries.id == task.series_id))
        series = series_result.scalar_one()
        logger.info("Удалена серия id=%s (scope=series)", series.id)
        await session.delete(series)  # каскадно удалит все Task серии
        await session.flush()
        return

    raise ValueError(f"Некорректный scope: {scope!r}, ожидается 'this' или 'series'")


DAY_STATE_EMPTY = "empty"  # ⚪ нет задач
DAY_STATE_PENDING = "pending"  # 🟡 есть задачи
DAY_STATE_DONE = "done"  # 🟢 все задачи выполнены
DAY_STATE_OVERDUE = "overdue"  # 🔴 есть просроченные задачи


async def _ensure_generated_for_range(session: AsyncSession, user: User, range_to: date) -> None:
    """
    Догенерировать экземпляры для всех активных серий пользователя вплоть до
    range_to. Нужно, когда WebApp запрашивает месяц/дату за пределами
    горизонта, заполненного при создании задачи (settings.task_generation_horizon_days).
    """
    result = await session.execute(
        select(TaskSeries).where(TaskSeries.user_id == user.id, TaskSeries.is_active.is_(True))
    )
    for series in result.scalars().all():
        if series.start_date > range_to:
            continue
        await ensure_series_generated(session, series, range_to)


async def list_tasks_for_period(
    session: AsyncSession, user: User, start: date, end: date
) -> list[Task]:
    await _ensure_generated_for_range(session, user, end)
    result = await session.execute(
        select(Task)
        .where(Task.user_id == user.id, Task.task_date >= start, Task.task_date <= end)
        .order_by(Task.task_date, Task.task_time, Task.created_at)
    )
    return list(result.scalars().all())


def classify_day_states(tasks: list[Task], today: date) -> dict[date, str]:
    """
    Группирует задачи по дате и определяет состояние дня (⚪🟡🟢🔴).
    Общая логика для календаря (get_month_overview) и статистики в
    stats_service — правило должно быть одно и то же в обоих местах.
    """
    by_date: dict[date, list[Task]] = {}
    for t in tasks:
        by_date.setdefault(t.task_date, []).append(t)

    states: dict[date, str] = {}
    for day, day_tasks in by_date.items():
        if any(t.status == TaskStatus.MISSED for t in day_tasks):
            states[day] = DAY_STATE_OVERDUE
        elif day < today and any(t.status == TaskStatus.PENDING for t in day_tasks):
            states[day] = DAY_STATE_OVERDUE
        elif all(t.status == TaskStatus.DONE for t in day_tasks):
            states[day] = DAY_STATE_DONE
        else:
            states[day] = DAY_STATE_PENDING
    return states


async def get_month_overview(session: AsyncSession, user: User, year: int, month: int) -> dict[date, str]:
    """Состояние каждого дня месяца для раскраски календаря (⚪🟡🟢🔴)."""
    first_day = date(year, month, 1)
    next_month_first = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day = next_month_first - timedelta(days=1)

    tasks = await list_tasks_for_period(session, user, first_day, last_day)
    return classify_day_states(tasks, date.today())


async def set_task_status(session: AsyncSession, task: Task, status: TaskStatus) -> Task:
    task.status = status
    task.completed_at = datetime.now() if status == TaskStatus.DONE else None
    await session.flush()

    session.add(
        TaskHistory(
            user_id=task.user_id,
            task_id=task.id,
            task_title=task.title,
            task_date=task.task_date,
            status=status,
        )
    )
    await session.flush()
    logger.info("Статус задачи id=%s изменён на %s", task.id, status)
    return task

