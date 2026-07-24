"""
REST API для задач.

GET    /api/tasks?date=YYYY-MM-DD   — список задач на дату
POST   /api/tasks                   — создать задачу (разовую или серию)
PATCH  /api/tasks/{id}               — редактировать (scope=this|series)
POST   /api/tasks/{id}/move          — перенести (всегда только этот экземпляр)
POST   /api/tasks/{id}/status        — отметить статус (done/missed/pending)
DELETE /api/tasks/{id}?scope=this|series — удалить экземпляр или всю серию
"""

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status as http_status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, TaskStatus, User
from app.services import achievement_service, task_service
from app.services.exceptions import TaskNotFoundError, TaskNotOwnedError
from app.web.deps import get_current_user, get_db_session
from app.web.schemas import (
    AchievementOut,
    Scope,
    TaskCreateIn,
    TaskListOut,
    TaskMoveIn,
    TaskMutationOut,
    TaskOut,
    TaskStatusIn,
    TaskUpdateIn,
)

router = APIRouter(tags=["tasks"])


def _to_task_out(task: Task) -> TaskOut:
    return TaskOut(
        id=task.id,
        title=task.title,
        date=task.task_date,
        time=task.task_time,
        status=task.status.value,
        is_recurring=task.series_id is not None,
        repeat_type=task.series.repeat_type.value if task.series is not None else "once",
    )


async def _get_owned_task_or_404(session: AsyncSession, user: User, task_id: int) -> Task:
    try:
        return await task_service.get_owned_task(session, user, task_id)
    except TaskNotFoundError as exc:
        raise HTTPException(http_status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except TaskNotOwnedError as exc:
        raise HTTPException(http_status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.get("/tasks", response_model=TaskListOut)
async def get_tasks_for_date(
    date_: date = Query(..., alias="date"),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> TaskListOut:
    tasks = await task_service.list_tasks_for_date(session, user, date_)
    return TaskListOut(date=date_, tasks=[_to_task_out(t) for t in tasks])


@router.post("/tasks", response_model=TaskMutationOut, status_code=http_status.HTTP_201_CREATED)
async def create_task(
    payload: TaskCreateIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> TaskMutationOut:
    task = await task_service.create_task(
        session,
        user,
        title=payload.title,
        task_date=payload.date,
        task_time=payload.time,
        repeat_type=payload.repeat_type,
    )
    # get_owned_task для консистентного ответа с подгруженной series (repeat_type).
    task = await task_service.get_owned_task(session, user, task.id)
    return TaskMutationOut(task=_to_task_out(task))


@router.patch("/tasks/{task_id}", response_model=TaskMutationOut)
async def update_task(
    task_id: int,
    payload: TaskUpdateIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> TaskMutationOut:
    task = await _get_owned_task_or_404(session, user, task_id)
    try:
        task = await task_service.update_task(
            session,
            task,
            scope=payload.scope,
            title=payload.title,
            task_date=payload.date if payload.scope == "this" else None,
            task_time=payload.time,
            repeat_type=payload.repeat_type if payload.scope == "series" else None,
        )
    except ValueError as exc:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    return TaskMutationOut(task=_to_task_out(task))


@router.post("/tasks/{task_id}/move", response_model=TaskMutationOut)
async def move_task(
    task_id: int,
    payload: TaskMoveIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> TaskMutationOut:
    task = await _get_owned_task_or_404(session, user, task_id)
    task = await task_service.move_task(session, task, payload.date, payload.time)
    return TaskMutationOut(task=_to_task_out(task))


@router.post("/tasks/{task_id}/status", response_model=TaskMutationOut)
async def set_task_status(
    task_id: int,
    payload: TaskStatusIn,
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> TaskMutationOut:
    task = await _get_owned_task_or_404(session, user, task_id)
    task = await task_service.set_task_status(session, task, TaskStatus(payload.status))
    # Только смена статуса может разблокировать достижение (счётчики
    # выполненных задач, серии, "без пропусков") — остальные мутации задач
    # на эти показатели не влияют.
    new_achievements = await achievement_service.check_and_award(session, user)
    return TaskMutationOut(
        task=_to_task_out(task),
        new_achievements=[
            AchievementOut(
                code=a.code, title=a.title, description=a.description, icon=a.icon, unlocked=True
            )
            for a in new_achievements
        ],
    )


@router.delete("/tasks/{task_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_task(
    task_id: int,
    scope: Scope = Query(...),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> None:
    task = await _get_owned_task_or_404(session, user, task_id)
    try:
        await task_service.delete_task(session, task, scope=scope)
    except ValueError as exc:
        raise HTTPException(http_status.HTTP_400_BAD_REQUEST, str(exc)) from exc
