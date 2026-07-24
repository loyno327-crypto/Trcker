"""GET /api/achievements — весь каталог достижений с отметкой, разблокировано ли у пользователя."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services import achievement_service
from app.web.deps import get_current_user, get_db_session
from app.web.schemas import AchievementOut, AchievementsOut

router = APIRouter(tags=["achievements"])


@router.get("/achievements", response_model=AchievementsOut)
async def get_achievements(
    session: AsyncSession = Depends(get_db_session),
    user: User = Depends(get_current_user),
) -> AchievementsOut:
    pairs = await achievement_service.list_achievements(session, user)
    return AchievementsOut(
        achievements=[
            AchievementOut(
                code=a.code,
                title=a.title,
                description=a.description,
                icon=a.icon,
                unlocked=unlocked_at is not None,
                unlocked_at=unlocked_at,
            )
            for a, unlocked_at in pairs
        ]
    )
