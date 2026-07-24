"""
Генерирует валидно подписанный Telegram WebApp initData для ручного
тестирования REST API без запуска настоящего Telegram-клиента.

Использование:

    python -m scripts.make_test_init_data [telegram_id] [first_name]

Выводит готовое значение заголовка:

    Authorization: tma <initData>

которое можно сразу вставить в curl или в Swagger UI (/docs -> Authorize).
"""

import hashlib
import hmac
import json
import sys
import time
from urllib.parse import urlencode

from app.config import settings


def build_init_data(telegram_id: int, first_name: str, username: str | None = None) -> str:
    user = {"id": telegram_id, "first_name": first_name}
    if username:
        user["username"] = username

    params = {
        "user": json.dumps(user, separators=(",", ":")),
        "auth_date": str(int(time.time())),
        "query_id": "AAtest",
    }

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret_key = hmac.new(b"WebAppData", settings.bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    params["hash"] = computed_hash
    return urlencode(params)


if __name__ == "__main__":
    tg_id = int(sys.argv[1]) if len(sys.argv) > 1 else 123456789
    name = sys.argv[2] if len(sys.argv) > 2 else "Тест"

    init_data = build_init_data(tg_id, name)
    print("Authorization: tma " + init_data)
