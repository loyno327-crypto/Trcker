"""
Вычисление дат повторяющейся серии задач.

Отделено от task_service.py, чтобы правило повторения можно было
переиспользовать (например, для превью в UI) и легко расширять новыми
типами повторений (CUSTOM) без изменения остальной бизнес-логики.
"""

from calendar import monthrange
from datetime import date, timedelta

from app.models import RepeatType


def dates_for_series(
    repeat_type: RepeatType,
    start_date: date,
    range_from: date,
    range_to: date,
) -> list[date]:
    """
    Возвращает список дат в диапазоне [range_from, range_to] (включительно),
    на которые приходится серия с данным правилом повторения.

    Даты раньше start_date никогда не включаются.
    """
    if range_to < range_from:
        return []

    effective_from = max(range_from, start_date)
    if effective_from > range_to:
        return []

    if repeat_type == RepeatType.ONCE:
        return [start_date] if range_from <= start_date <= range_to else []

    if repeat_type == RepeatType.DAILY:
        return _every_day(effective_from, range_to)

    if repeat_type == RepeatType.WEEKDAYS:
        return [d for d in _every_day(effective_from, range_to) if d.weekday() < 5]

    if repeat_type == RepeatType.WEEKENDS:
        return [d for d in _every_day(effective_from, range_to) if d.weekday() >= 5]

    if repeat_type == RepeatType.WEEKLY:
        return _weekly(start_date, effective_from, range_to)

    if repeat_type == RepeatType.MONTHLY:
        return _monthly(start_date, effective_from, range_to)

    # RepeatType.CUSTOM зарезервирован под будущие правила — пока не поддержан
    return []


def _every_day(range_from: date, range_to: date) -> list[date]:
    days = (range_to - range_from).days
    return [range_from + timedelta(days=i) for i in range(days + 1)]


def _weekly(start_date: date, range_from: date, range_to: date) -> list[date]:
    offset = (range_from - start_date).days % 7
    first = range_from if offset == 0 else range_from + timedelta(days=7 - offset)
    result = []
    current = first
    while current <= range_to:
        result.append(current)
        current += timedelta(days=7)
    return result


def _monthly(start_date: date, range_from: date, range_to: date) -> list[date]:
    """Та же дата числа месяца, что и start_date. Месяцы без такого числа пропускаются."""
    result = []
    year, month = range_from.year, range_from.month
    while True:
        last_day_of_month = monthrange(year, month)[1]
        if start_date.day <= last_day_of_month:
            candidate = date(year, month, start_date.day)
            if range_from <= candidate <= range_to:
                result.append(candidate)
            elif candidate > range_to:
                break
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        if date(year, month, 1) > range_to:
            break
    return result
