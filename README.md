# Трекер привычек и распорядка дня — Telegram-бот + WebApp

Статус разработки, полный текст ТЗ и подробный лог по этапам — в
[`PROGRESS.md`](./PROGRESS.md). Этот файл — только про запуск.

## Установка

```bash
cd habit_tracker
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# впишите в .env свой BOT_TOKEN (получить у @BotFather)
```

## Запуск бота (long polling)

```bash
python -m app.bot
```

Отвечает на `/start`, создаёт файл `habit_tracker.db` (SQLite) с таблицами.

## Запуск REST API для WebApp

```bash
uvicorn app.web.main:app --reload --port 8000
```

Документация (Swagger UI): http://localhost:8000/docs

Все эндпоинты требуют заголовок `Authorization: tma <initData>` — это
`Telegram.WebApp.initData`, который сама Telegram передаёт странице при
открытии WebApp внутри клиента. Для ручного теста без реального
Telegram-клиента:

```bash
python -m scripts.make_test_init_data
```

выведет готовую строку заголовка — вставить её в Swagger UI (кнопка
Authorize) или в `curl -H "Authorization: tma <initData>"`.

## Открыть сам WebApp (фронтенд)

Страница WebApp отдаётся на корне того же сервера (`http://localhost:8000/`).
Внутри настоящего Telegram-клиента она сама получает `initData`. Чтобы
открыть и проверить её в обычном браузере, добавьте initData из скрипта выше
как query-параметр:

```
http://localhost:8000/?init_data=<строка из вывода скрипта, без "Authorization: tma ">
```

## Деплой на BotHost

BotHost (как и большинство хостингов ботов) запускает **один процесс из
одного файла**, а не бота и веб-сервер по отдельности. Для этого в корне
проекта есть `main.py` — он поднимает и Telegram-бота (polling), и
FastAPI-сервер WebApp в одном процессе одновременно. Команды разработки из
разделов выше (`python -m app.bot`, отдельный `uvicorn ...`) по-прежнему
подходят для локальной разработки, а `main.py` — специально для хостинга.

Настройка в панели BotHost:

1. Язык проекта — **Python** (не Node.js: в репозитории есть `.js`-файл
   (`app/web/static/js/app.js`) — это чисто клиентский код для WebApp,
   выполняется в браузере/Telegram, к запуску самого Python-проекта
   отношения не имеет и Node.js не требует).
2. Стартовый файл — **`main.py`** (лежит в корне проекта).
3. Зависимости — `requirements.txt` (тоже в корне).
4. Переменные окружения — как минимум `BOT_TOKEN` и `WEBAPP_URL` (см.
   `.env.example`). `WEBAPP_URL` — это HTTPS-домен, который BotHost выдаёт
   проекту; его же нужно указать в BotFather как WebApp URL.
5. Порт — вручную настраивать не нужно: если BotHost передаёт порт через
   переменную окружения `PORT`, `main.py` слушает именно его; если нет —
   берётся `WEB_PORT` из `.env` (по умолчанию 8000).
6. База данных — по умолчанию SQLite-файл рядом с кодом. Если диск на
   хостинге не персистентный между перезапусками — сменить `DATABASE_URL` на
   внешнюю БД (например, PostgreSQL), архитектура это уже поддерживает без
   изменения кода.

## Структура проекта

```
main.py             — точка входа для хостингов (бот + веб-сервер в одном
                       процессе, см. раздел "Деплой на BotHost" выше)
app/
  bot.py            — точка входа Telegram-бота отдельно (для разработки)
  config.py         — настройки из .env
  database.py       — SQLAlchemy engine/сессии
  models.py         — ORM-модели
  scheduler.py       — напоминания (реализуется позже)
  handlers/          — хендлеры aiogram
  services/           — бизнес-логика (задачи, пользователи, повторения)
  web/
    main.py          — FastAPI-приложение
    routers/          — REST API эндпоинты
    telegram_auth.py  — проверка initData
    static/           — фронтенд WebApp (HTML/CSS/JS), смонтирован на "/"
    templates/        — не используется (SPA-статика вместо Jinja-шаблонов)
scripts/             — вспомогательные dev-скрипты
```

Проект пишется строго поэтапно — каждый этап полностью рабочий, следующий
начинается только после подтверждения. Текущий статус — в `PROGRESS.md`.
