"""
Проверка Telegram WebApp initData.

Алгоритм из официальной документации Telegram:
https://core.telegram.org/bots/webapps#validating-data-received-via-the-web-app

secret_key = HMAC_SHA256(key="WebAppData", msg=bot_token)
hash_check = HMAC_SHA256(key=secret_key, msg=data_check_string)

data_check_string — все пары "key=value" из initData (кроме hash),
отсортированные по ключу и соединённые через "\n".
"""

import hashlib
import hmac
import json
import time
from urllib.parse import parse_qsl

from app.config import settings
from app.logger import get_logger

logger = get_logger(__name__)

# Сколько секунд считаем initData свежим (Telegram присылает auth_date).
MAX_INIT_DATA_AGE_SECONDS = 24 * 60 * 60


class TelegramAuthError(Exception):
    """initData отсутствует, повреждён, просрочен или подпись не совпадает."""


def parse_and_validate_init_data(init_data: str) -> dict:
    """Возвращает {"raw": {...}, "user": {...}} либо бросает TelegramAuthError."""
    if not init_data:
        raise TelegramAuthError("Пустой init_data")

    try:
        pairs = dict(parse_qsl(init_data, strict_parsing=True))
    except ValueError as exc:
        raise TelegramAuthError("Некорректный формат init_data") from exc

    received_hash = pairs.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("Отсутствует hash в init_data")

    data_check_string = "\n".join(f"{key}={value}" for key, value in sorted(pairs.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise TelegramAuthError("Неверная подпись init_data")

    auth_date = pairs.get("auth_date")
    if auth_date and (time.time() - int(auth_date)) > MAX_INIT_DATA_AGE_SECONDS:
        raise TelegramAuthError("init_data устарел")

    user_raw = pairs.get("user")
    if not user_raw:
        raise TelegramAuthError("В init_data отсутствует user")

    try:
        user_data = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("Некорректный формат user в init_data") from exc

    return {"raw": pairs, "user": user_data}
