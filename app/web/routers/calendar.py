"""GET /api/calendar — состояние каждого дня месяца для главной страницы WebApp."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import task_service
from app.web.deps import get_current_user, get_db_session
from app.web.schemas import CalendarOut, DayStateOut

router = APIRouter(tags=["calendar"])


@router.get("/calendar", response_model=CalendarOut)
async def get_calendar(
    year: int = Query(..., ge=2020, le=2100),
    month: int = Query(..., ge=1, le=12),
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> CalendarOut:
    states = await task_service.get_month_overview(session, user, year, month)
    days = [DayStateOut(date=d, state=s) for d, s in sorted(states.items())]
    return CalendarOut(year=year, month=month, days=days)
