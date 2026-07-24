"""
FastAPI-приложение: REST API + статика фронтенда для Telegram WebApp.

REST-эндпоинты: календарь, задачи (CRUD + статус + перенос), история/статистика,
достижения.
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import init_db
from app.logger import get_logger, setup_logging
from app.web.routers import achievements, calendar, history, tasks

STATIC_DIR = Path(__file__).parent / "static"

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    await init_db()
    logger.info("FastAPI-приложение запущено")
    yield


app = FastAPI(title="Habit Tracker WebApp API", lifespan=lifespan)

# WebApp открывается внутри Telegram (WebView), а не с фиксированного домена
# браузера — ограничивать origin нет смысла, доступ и так закрыт проверкой initData.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(calendar.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(achievements.router, prefix="/api")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Фронтенд WebApp (index.html, css, js) — статика, без шаблонизатора: страница
# сама делает запросы к /api/* с заголовком Authorization: tma <initData>.
# Смонтировано последним, после /api и /health, чтобы точные маршруты API
# оставались в приоритете.
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
