"""Pydantic-схемы запросов и ответов REST API для WebApp."""

from datetime import date as Date, datetime, time as Time
from typing import Literal

from pydantic import BaseModel, Field

from app.models import RepeatType


class AchievementOut(BaseModel):
    code: str
    title: str
    description: str
    icon: str
    unlocked: bool
    unlocked_at: datetime | None = None


class AchievementsOut(BaseModel):
    achievements: list[AchievementOut]


class DayStateOut(BaseModel):
    date: Date
    state: str  # empty | pending | done | overdue


class CalendarOut(BaseModel):
    year: int
    month: int
    days: list[DayStateOut]


class TaskOut(BaseModel):
    id: int
    title: str
    date: Date
    time: Time
    status: str  # pending | done | missed
    is_recurring: bool
    repeat_type: str


class TaskListOut(BaseModel):
    date: Date
    tasks: list[TaskOut]


# Что вернуть после мутации — тот же формат, что и в списке, чтобы фронтенду
# не нужно было запрашивать список заново ради одной задачи.
# new_achievements заполняется только эндпоинтом смены статуса (/status) —
# остальные мутации на достижения не влияют, там всегда пустой список.
class TaskMutationOut(BaseModel):
    task: TaskOut
    new_achievements: list[AchievementOut] = Field(default_factory=list)


class TaskCreateIn(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    date: Date
    time: Time
    repeat_type: RepeatType = RepeatType.ONCE


Scope = Literal["this", "series"]


class TaskUpdateIn(BaseModel):
    scope: Scope
    title: str | None = Field(default=None, min_length=1, max_length=255)
    date: Date | None = None  # применяется только при scope="this"
    time: Time | None = None
    repeat_type: RepeatType | None = None  # применяется только при scope="series"


class TaskMoveIn(BaseModel):
    date: Date
    time: Time


class TaskStatusIn(BaseModel):
    status: Literal["done", "missed", "pending"]


HistoryPeriod = Literal["today", "week", "month", "all"]


class HistoryTaskOut(BaseModel):
    id: int
    title: str
    date: Date
    time: Time
    status: str


class MostProductiveDayOut(BaseModel):
    date: Date
    done_count: int


class HistoryOut(BaseModel):
    period: HistoryPeriod
    start: Date
    end: Date
    done_count: int
    missed_count: int
    percent: int
    current_streak: int
    best_streak: int
    most_productive_day: MostProductiveDayOut | None
    recent_done: list[HistoryTaskOut]
    recent_missed: list[HistoryTaskOut]
