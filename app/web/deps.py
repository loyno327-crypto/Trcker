"""FastAPI-зависимости: сессия БД и текущий пользователь из Telegram WebApp initData."""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.models import User
from app.services.user_service import get_or_create_user
from app.web.telegram_auth import TelegramAuthError, parse_and_validate_init_data

# Заново экспортируем как зависимость с понятным для веб-слоя именем.
get_db_session = get_session


async def get_init_data_user(authorization: str | None = Header(default=None)) -> dict:
    """
    Ожидает заголовок:  Authorization: tma <initData>
    где <initData> — это строка Telegram.WebApp.initData, как есть, без декодирования.
    """
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Ожидается заголовок Authorization: tma <initData>",
        )

    init_data = authorization.removeprefix("tma ").strip()
    try:
        parsed = parse_and_validate_init_data(init_data)
    except TelegramAuthError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    return parsed["user"]


async def get_current_user(
    session: AsyncSession = Depends(get_db_session),
    tg_user: dict = Depends(get_init_data_user),
) -> User:
    return await get_or_create_user(
        session,
        telegram_id=tg_user["id"],
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name"),
    )
