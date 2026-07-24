"""GET /api/history?period=today|week|month|all — статистика для страницы «История»."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task, User
from app.services import stats_service
from app.web.deps import get_current_user, get_db_session
from app.web.schemas import HistoryOut, HistoryPeriod, HistoryTaskOut, MostProductiveDayOut

router = APIRouter(tags=["history"])


def _to_history_task_out(task: Task) -> HistoryTaskOut:
    return HistoryTaskOut(id=task.id, title=task.title, date=task.task_date, time=task.task_time, status=task.status.value)


@router.get("/history", response_model=HistoryOut)
async def get_history(
    period: HistoryPeriod = Query("today"),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> HistoryOut:
    stats = await stats_service.get_history(session, user, period)
    return HistoryOut(
        period=stats["period"],
        start=stats["start"],
        end=stats["end"],
        done_count=stats["done_count"],
        missed_count=stats["missed_count"],
        percent=stats["percent"],
        current_streak=stats["current_streak"],
        best_streak=stats["best_streak"],
        most_productive_day=(
            MostProductiveDayOut(**stats["most_productive_day"]) if stats["most_productive_day"] else None
        ),
        recent_done=[_to_history_task_out(t) for t in stats["recent_done"]],
        recent_missed=[_to_history_task_out(t) for t in stats["recent_missed"]],
    )
