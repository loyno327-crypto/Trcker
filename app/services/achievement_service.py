"""
Достижения: каталог (см. models.Achievement) + правила разблокировки.

Каталог хранится в БД, а не хардкодится в шаблонах фронтенда — это и есть
требование ТЗ "архитектура должна позволять легко добавлять новые
достижения". Сама структура каталога (ACHIEVEMENT_CATALOG ниже) — единственное
место, которое нужно менять для нового достижения: сидинг в БД (см.
app.database.seed_achievements) и правило разблокировки (CHECKERS) уже
устроены так, что новый код в каталоге подхватывается автоматически, нужно
только дописать для него один checker.

check_and_award вызывается после любого изменения статуса задачи
(app.services.task_service.set_task_status) — и в веб-API, и в хендлере
кнопок напоминания бота. Разблокированные достижения не отбираются обратно,
даже если статистика впоследствии "ухудшится" (например, пользователь снял
отметку с задачи) — это принятая практика в трекерах привычек: достижение
остаётся как исторический факт, а не текущий статус.

Правила для "N дней подряд" (🔥/🏆) используют ту же серию, что и статистика
на странице «История» (app.services.stats_service.compute_streaks,
best_streak) — день без единой задачи не в счёт, обрывает серию только
просроченный день.

Правила "без пропусков за неделю/месяц" (📅/🌟) — отдельная, более узкая
метрика: она смотрит только на фиксированное скользящее окно завершившихся
календарных дней (последние 7 или 30 дней ДО сегодня, сегодня не в счёт — оно
может быть ещё не завершено) и требует, чтобы среди дней-с-задачами в этом
окне не было ни одного просроченного. В отличие от "N дней подряд", здесь не
обязательно, чтобы КАЖДЫЙ день окна содержал задачи, и более ранняя история
(что было до этого окна) не важна — считается только это конкретное окно.
Поэтому это осознанно разные достижения, а не дубликаты: можно получить
"неделю без пропусков", даже если самая длинная серия короче 7 (например,
из-за "пустых" дней внутри недели), и наоборот.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logger import get_logger
from app.models import Achievement, TaskStatus, User, UserAchievement
from app.services.stats_service import ALL_TIME_START, compute_streaks
from app.services.task_service import (
    DAY_STATE_OVERDUE,
    classify_day_states,
    list_tasks_for_period,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class AchievementDef:
    code: str
    title: str
    description: str
    icon: str


# Порядок в каталоге — он же порядок отображения на экране «История»
# (см. app.services.achievement_service.list_achievements).
ACHIEVEMENT_CATALOG: list[AchievementDef] = [
    AchievementDef(
        code="first_done",
        title="Первая выполненная задача",
        description="Выполните свою первую задачу в трекере",
        icon="🎉",
    ),
    AchievementDef(
        code="streak_7",
        title="7 дней подряд",
        description="Выполняйте все задачи дня 7 дней подряд",
        icon="🔥",
    ),
    AchievementDef(
        code="streak_30",
        title="30 дней подряд",
        description="Выполняйте все задачи дня 30 дней подряд",
        icon="🏆",
    ),
    AchievementDef(
        code="done_100",
        title="Выполнено 100 задач",
        description="Выполните 100 задач за всё время",
        icon="💯",
    ),
    AchievementDef(
        code="done_500",
        title="Выполнено 500 задач",
        description="Выполните 500 задач за всё время",
        icon="⭐",
    ),
    AchievementDef(
        code="week_clean",
        title="Неделя без пропусков",
        description="Ни одной просроченной задачи за последние 7 дней",
        icon="📅",
    ),
    AchievementDef(
        code="month_clean",
        title="Месяц без пропусков",
        description="Ни одной просроченной задачи за последние 30 дней",
        icon="🌟",
    ),
]


def _clean_window(day_states: dict[date, str], today: date, window_days: int) -> bool:
    """Среди дней-с-задачами за последние window_days завершившихся
    календарных дней (today не включается) нет ни одного просроченного, и
    таких дней вообще было хотя бы 1 (иначе достижение выдавалось бы сразу
    новому пользователю без единой задачи)."""
    window_start = today - timedelta(days=window_days)
    days_in_window = [d for d in day_states if window_start <= d < today]
    if not days_in_window:
        return False
    return all(day_states[d] != DAY_STATE_OVERDUE for d in days_in_window)


async def _build_snapshot(session: AsyncSession, user: User) -> dict:
    """Собирает всё, что нужно правилам CHECKERS, одним проходом по задачам
    пользователя — так же, как это делает stats_service.get_history."""
    today = date.today()
    all_tasks = await list_tasks_for_period(session, user, ALL_TIME_START, today)
    done_count = sum(1 for t in all_tasks if t.status == TaskStatus.DONE)

    day_states = classify_day_states(all_tasks, today)
    _, best_streak = compute_streaks(day_states, today)

    return {
        "done_count": done_count,
        "best_streak": best_streak,
        "week_clean": _clean_window(day_states, today, 7),
        "month_clean": _clean_window(day_states, today, 30),
    }


CHECKERS = {
    "first_done": lambda s: s["done_count"] >= 1,
    "streak_7": lambda s: s["best_streak"] >= 7,
    "streak_30": lambda s: s["best_streak"] >= 30,
    "done_100": lambda s: s["done_count"] >= 100,
    "done_500": lambda s: s["done_count"] >= 500,
    "week_clean": lambda s: s["week_clean"],
    "month_clean": lambda s: s["month_clean"],
}


async def check_and_award(session: AsyncSession, user: User) -> list[Achievement]:
    """Проверяет все правила и разблокирует новые достижения пользователя.
    Возвращает только что разблокированные (для тоста в WebApp / сообщения
    бота) — уже разблокированные раньше повторно не возвращаются."""
    snapshot = await _build_snapshot(session, user)

    unlocked_result = await session.execute(
        select(UserAchievement.achievement_id).where(UserAchievement.user_id == user.id)
    )
    already_unlocked_ids = set(unlocked_result.scalars().all())

    catalog_result = await session.execute(select(Achievement))
    by_code = {a.code: a for a in catalog_result.scalars().all()}

    newly_unlocked: list[Achievement] = []
    for code, check in CHECKERS.items():
        achievement = by_code.get(code)
        if achievement is None or achievement.id in already_unlocked_ids:
            continue
        if check(snapshot):
            session.add(UserAchievement(user_id=user.id, achievement_id=achievement.id))
            newly_unlocked.append(achievement)

    if newly_unlocked:
        await session.flush()
        logger.info(
            "Пользователю user_id=%s разблокированы достижения: %s",
            user.id, [a.code for a in newly_unlocked],
        )
    return newly_unlocked


async def list_achievements(
    session: AsyncSession, user: User
) -> list[tuple[Achievement, datetime | None]]:
    """Весь каталог достижений с датой разблокировки у пользователя (None,
    если ещё не разблокировано). Порядок — как в ACHIEVEMENT_CATALOG (порядок
    появления в БД при сидинге не гарантирован при до-сеивании новых
    достижений более поздней версией)."""
    catalog_result = await session.execute(select(Achievement))
    by_code = {a.code: a for a in catalog_result.scalars().all()}

    unlocked_result = await session.execute(
        select(UserAchievement.achievement_id, UserAchievement.unlocked_at).where(
            UserAchievement.user_id == user.id
        )
    )
    unlocked_at_by_id = {row.achievement_id: row.unlocked_at for row in unlocked_result}

    ordered: list[tuple[Achievement, datetime | None]] = []
    for definition in ACHIEVEMENT_CATALOG:
        achievement = by_code.get(definition.code)
        if achievement is None:
            continue  # ещё не досеян (например, только что добавлен в каталог)
        ordered.append((achievement, unlocked_at_by_id.get(achievement.id)))
    return ordered
