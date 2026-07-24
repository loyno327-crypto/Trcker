"""
ORM-модели проекта.

Схема:

User 1 --- N TaskSeries 1 --- N Task 1 --- N TaskHistory
User 1 --- N Task (через series, но и series может быть None -> разовая задача)
User N --- N Achievement (через UserAchievement)

TaskSeries описывает "шаблон" повторяющейся задачи (или разовой — repeat_type=ONCE).
Task — конкретный экземпляр задачи на конкретную дату (то, что видит пользователь
в календаре/списке). Такое разделение нужно, чтобы можно было редактировать/удалять
либо только один экземпляр, либо всю серию сразу (требование ТЗ).
"""

import enum
from datetime import date, datetime, time

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RepeatType(str, enum.Enum):
    ONCE = "once"  # один раз
    DAILY = "daily"  # каждый день
    WEEKDAYS = "weekdays"  # по будням
    WEEKENDS = "weekends"  # по выходным
    WEEKLY = "weekly"  # каждую неделю (в тот же день недели, что start_date)
    MONTHLY = "monthly"  # каждый месяц (то же число, что start_date)
    CUSTOM = "custom"  # зарезервировано под будущие пользовательские правила


class TaskStatus(str, enum.Enum):
    PENDING = "pending"  # ещё не наступило / не отмечено
    DONE = "done"  # выполнено
    MISSED = "missed"  # не выполнено (просрочено и отмечено, либо авто-просрочка)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer, unique=True, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    task_series: Mapped[list["TaskSeries"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    history: Mapped[list["TaskHistory"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    achievements: Mapped[list["UserAchievement"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} telegram_id={self.telegram_id}>"


class TaskSeries(Base):
    """Шаблон задачи. Для разовой задачи repeat_type=ONCE и у неё ровно один Task."""

    __tablename__ = "task_series"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    title: Mapped[str] = mapped_column(String(255))
    repeat_type: Mapped[RepeatType] = mapped_column(Enum(RepeatType), default=RepeatType.ONCE)

    start_date: Mapped[date] = mapped_column(Date)
    time: Mapped[time] = mapped_column(Time)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # До какой даты уже сгенерированы экземпляры Task для этой серии.
    # Генерация всегда идёт только вперёд от этой отметки — благодаря этому
    # перенос/редактирование одного экземпляра не приводит к тому, что для
    # его старой даты повторно создастся задача.
    last_generated_until: Mapped[date | None] = mapped_column(Date, nullable=True)

    user: Mapped["User"] = relationship(back_populates="task_series")
    tasks: Mapped[list["Task"]] = relationship(
        back_populates="series", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<TaskSeries id={self.id} title={self.title!r} repeat={self.repeat_type}>"


class Task(Base):
    """Конкретный экземпляр задачи на конкретную дату — то, что видит пользователь."""

    __tablename__ = "tasks"
    __table_args__ = (UniqueConstraint("series_id", "task_date", name="uq_series_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    series_id: Mapped[int | None] = mapped_column(
        ForeignKey("task_series.id", ondelete="CASCADE"), nullable=True
    )

    # Денормализованы, чтобы отдельный экземпляр можно было переименовать/сдвинуть,
    # не трогая остальную серию ("изменить только эту задачу").
    title: Mapped[str] = mapped_column(String(255))
    task_date: Mapped[date] = mapped_column(Date, index=True)
    task_time: Mapped[time] = mapped_column(Time)

    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus), default=TaskStatus.PENDING)

    reminder_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user: Mapped["User"] = relationship(back_populates="tasks")
    series: Mapped["TaskSeries | None"] = relationship(back_populates="tasks")
    history_entries: Mapped[list["TaskHistory"]] = relationship(
        back_populates="task", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Task id={self.id} title={self.title!r} date={self.task_date} status={self.status}>"


class TaskHistory(Base):
    """
    Лог событий по задачам — основа для страницы "История" и статистики
    (серии, проценты выполнения и т.д.), не зависящий от текущего состояния Task.
    """

    __tablename__ = "task_history"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"))

    task_title: Mapped[str] = mapped_column(String(255))
    task_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[TaskStatus] = mapped_column(Enum(TaskStatus))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="history")
    task: Mapped["Task"] = relationship(back_populates="history_entries")

    def __repr__(self) -> str:
        return f"<TaskHistory task_id={self.task_id} date={self.task_date} status={self.status}>"


class Achievement(Base):
    """
    Каталог достижений. Хранится в БД (не хардкод), чтобы новые достижения
    можно было добавлять без изменения кода — только новой строкой в таблице
    плюс правилом проверки в AchievementService (Этап "Достижения").
    """

    __tablename__ = "achievements"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(50), unique=True)  # напр. "streak_7"
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(String(500))
    icon: Mapped[str] = mapped_column(String(10))  # emoji

    users: Mapped[list["UserAchievement"]] = relationship(
        back_populates="achievement", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Achievement code={self.code!r}>"


class UserAchievement(Base):
    """Связь пользователь <-> полученное достижение (many-to-many + дата получения)."""

    __tablename__ = "user_achievements"
    __table_args__ = (UniqueConstraint("user_id", "achievement_id", name="uq_user_achievement"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    achievement_id: Mapped[int] = mapped_column(ForeignKey("achievements.id", ondelete="CASCADE"))
    unlocked_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="achievements")
    achievement: Mapped["Achievement"] = relationship(back_populates="users")
