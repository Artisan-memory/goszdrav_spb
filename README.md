# Goszdrav SPB Bot

Проект для Telegram-бота и Telegram Mini App, который помогает мониторить номерки на портале Госздрав СПб и, в зависимости от режима наблюдения, либо уведомлять пользователя, либо пытаться пройти шаг автозаписи.

Целевой портал:

- [gorzdrav.spb.ru/service-free-schedule](https://gorzdrav.spb.ru/service-free-schedule)

Актуальная версия `aiogram`, на которую собран проект:

- [aiogram 3.26.0 на PyPI](https://pypi.org/project/aiogram/)

---

## 1. Что делает система

Система разделена на два слоя:

### Профиль пользователя

Профиль хранит только стабильные данные:

- ФИО
- email
- дата рождения
- район
- медорганизация

Это базовая привязка пользователя к своей поликлинике.

### Наблюдения

Наблюдение хранит динамическую цель мониторинга:

- специальность
- опционально конкретного врача
- режим:
  - `notify`
  - `autobook`

Именно наблюдения проверяются воркером в фоне.

---

## 2. Пользовательский сценарий

### Режим `notify`

Когда система находит номерок:

- пользователю приходит Telegram-уведомление
- в сообщении есть краткая сводка
- в сообщении есть прямая ссылка на расписание

### Режим `autobook`

Когда система находит номерок:

- выполняется попытка пройти шаг записи
- используется профиль пользователя
- если врач в наблюдении не выбран, система выбирает врача по стратегии автозаписи, заданной в наблюдении
- если получилось пройти до подтверждения или дальше, это фиксируется в БД
- пользователю приходит отдельное сообщение с результатом попытки автозаписи

Важно:

- автозапись сейчас реализована эвристически, потому что DOM и финальный шаг портала могут меняться
- система уже умеет выбирать талон по стратегии, кликать его, нажимать `Записаться`, заполнять известные поля и фиксировать итог

---

## 3. Основные компоненты

```text
src/goszdrav_bot/
├── api/                   # FastAPI backend и Mini App endpoints
├── bot/                   # Telegram bot на aiogram
├── core/                  # константы районов и общие утилиты
├── db/                    # SQLAlchemy ORM модели и async session
├── schemas/               # Pydantic схемы API
├── scraper/               # direct API client Госздрава + Selenium для автозаписи
├── services/              # бизнес-логика профиля, наблюдений, мониторинга
├── webapp/                # HTML/CSS/JS для Telegram Mini App
└── workers/               # фоновой мониторинг наблюдений
```

---

## 4. Архитектурная модель

### Бот

Бот отвечает за:

- `/start`
- `/profile`
- первичное меню
- fallback chat wizard для профиля
- live-поиск медорганизации в чате через inline-кнопки

Бот не хранит бизнес-логику scraping внутри handlers. Всё важное вынесено в `services/` и `api/`.

### Mini App

Mini App отвечает за:

- редактирование профиля
- выбор поликлиники из live-каталога
- динамический поиск по названию и адресу
- создание наблюдений
- ручной скан выбранного наблюдения
- просмотр текущего состояния наблюдений
- большой preview расписания и номерков

### API

FastAPI слой отвечает за:

- профили
- каталог медорганизаций/специальностей/врачей
- расписание
- CRUD наблюдений
- ручной запуск сканирования наблюдения

### Scraper

Scraper отвечает за:

- чтение каталога, врачей и расписаний через backend API Госздрава
- попытку автозаписи через Selenium flow на публичной странице

### Worker

Worker отвечает за:

- периодический обход активных наблюдений
- запись результатов сканов
- дедупликацию уведомлений
- отправку Telegram-сообщений
- запуск попытки автозаписи

---

## 5. Схема данных

### `telegram_users`

Хранит Telegram-пользователя.

Поля:

- `telegram_id`
- `username`
- `first_name`
- `last_name`
- `language_code`

### `user_profiles`

Хранит профиль пациента.

Поля:

- `full_name_encrypted`
- `email_encrypted`
- `birth_date_encrypted`
- `district_code`
- `organization_external_id`
- `organization_label`
- `is_complete`

### `watch_targets`

Хранит наблюдения.

Поля:

- `district_code`
- `organization_external_id`
- `organization_label`
- `specialty_external_id`
- `specialty_label`
- `doctor_external_id`
- `doctor_label`
- `mode`
- `is_active`
- `latest_result_status`
- `latest_result_summary`
- `latest_result_url`
- `last_seen_slots_count`
- `last_checked_at`

### `scrape_events`

История сканов.

Поля:

- `status`
- `slots_count`
- `result_url`
- `summary`
- `payload_json`
- `happened_at`

### `user_notifications`

История отправленных уведомлений.

Поля:

- `kind`
- `fingerprint`
- `message_text`
- `direct_url`
- `sent_at`

### `booking_attempts`

История попыток автозаписи.

Поля:

- `status`
- `slot_time`
- `direct_url`
- `details`

---

## 6. Ключевые модули

### `src/goszdrav_bot/bot/commands.py`

Здесь определяется минимальный набор команд бота:

- `/start`
- `/profile`

Команды выставляются:

- при старте polling-процесса
- повторно при первом `/start`

### `src/goszdrav_bot/bot/handlers/profile.py`

Содержит:

- показ профиля
- fallback wizard
- чатовый поиск медорганизации с выдачей живых вариантов

Важно:

- wizard больше не настраивает специальность или врача
- wizard заполняет только профиль пользователя

### `src/goszdrav_bot/services/profile.py`

Центральный сервис профиля.

Что делает:

- создает пользователя при первом обращении
- обновляет профиль
- шифрует чувствительные поля
- сбрасывает привязку к медорганизации, если меняется район

### `src/goszdrav_bot/services/watch_targets.py`

Сервис наблюдений.

Что делает:

- создает наблюдения
- проверяет дубликаты
- обновляет статус наблюдений
- пишет события сканирования
- пишет уведомления
- пишет попытки автозаписи

### `src/goszdrav_bot/services/monitoring.py`

Главный orchestration-слой мониторинга.

Что делает:

- сканирует конкретное наблюдение
- пишет `scrape_events`
- при `notify` отправляет уведомление с прямой ссылкой
- при `autobook` пытается создать `booking_attempt`
- отправляет результат автозаписи пользователю
- защищает цикл мониторинга от отката транзакции при ошибках scraping/Telegram

### `src/goszdrav_bot/scraper/api_client.py`

Async клиент для backend API Госздрава.

Что умеет:

- поликлиники по району
- специальности по `lpuId`
- врачи по `specialityId`
- расписание врача
- доступные талоны

Использует реальные endpoint'ы вида:

- `/v2/shared/district/{districtId}/lpus`
- `/v2/schedule/lpu/{lpuId}/specialties`
- `/v2/schedule/lpu/{lpuId}/speciality/{specialityId}/doctors`
- `/v2/schedule/lpu/{lpuId}/doctor/{doctorId}/timetable`
- `/v2/schedule/lpu/{lpuId}/doctor/{doctorId}/appointments`

### `src/goszdrav_bot/scraper/selenium_client.py`

Sync Selenium клиент для шага автозаписи и fallback DOM-работы.

Что умеет:

- попытка автозаписи на талон, выбранный по стратегии наблюдения

### `src/goszdrav_bot/scraper/service.py`

Async facade над direct API и Selenium.

Зачем это нужно:

- чтение каталога и расписаний лучше делать без браузера
- Selenium всё еще нужен для best-effort автозаписи
- FastAPI и бот асинхронные
- worker тоже асинхронный

Решение:

- `ThreadPoolExecutor`
- `Semaphore`
- direct API для каталога и расписаний
- `run_in_executor(...)` только для шага бронирования

### `src/goszdrav_bot/workers/__main__.py`

Точка входа worker-процесса.

### `src/goszdrav_bot/workers/monitor.py`

Координирует обход активных наблюдений.

Сейчас worker:

- берет все активные наблюдения
- запускает скан конкурентно
- полагается на ограничение параллелизма scraper-а

---

## 7. API маршруты

### Профиль

- `GET /webapp/profile`
- `GET /api/v1/profile/me`
- `POST /api/v1/profile/me`

### Каталог

- `GET /api/v1/catalog/districts`
- `GET /api/v1/catalog/organizations`
- `GET /api/v1/catalog/specialties`
- `GET /api/v1/catalog/doctors`
- `GET /api/v1/catalog/schedule`

### Наблюдения

- `GET /api/v1/watch-targets`
- `POST /api/v1/watch-targets`
- `PATCH /api/v1/watch-targets/{id}`
- `DELETE /api/v1/watch-targets/{id}`
- `POST /api/v1/watch-targets/{id}/scan`

---

## 8. Как устроен flow Mini App

### Шаг 1. Профиль

Пользователь сохраняет:

- ФИО
- email
- дату рождения
- район
- медорганизацию из живого динамического поиска

### Шаг 2. Наблюдение

Пользователь выбирает:

- специальность
- врача или вариант `любой доступный врач`
- режим:
  - `Уведомлять`
  - `Автозапись`

Если выбран режим `Автозапись` и врач не указан, worker сначала собирает доступных врачей по специальности, потом выбирает лучшего кандидата по стратегии наблюдения.

Доступные стратегии:

- `Ближайшая дата, позднее время`
- `Ближайшая дата, раннее время`
- `Только утро`
- `Только вечер`

Если по выбранной специальности доступен только один врач:

- Mini App автоматически выбирает его
- preview расписания загружается сразу
- наблюдение создается уже с конкретным врачом, а не с абстрактным `любой врач`

### Шаг 3. Live preview

Если выбран конкретный врач:

- загружается расписание
- показываются доступные даты
- показываются талоны

### Шаг 4. Запуск наблюдения

Наблюдение попадает в БД и начинает обрабатываться worker-процессом.

---

## 9. Как работает дедуп уведомлений

Для уведомлений строится fingerprint на основе:

- `target_id`
- summary
- direct URL
- количества найденных талонов

Если такой fingerprint уже отправлялся недавно, повторное сообщение не отправляется.

Важно:

- fingerprint не является глобально уникальным навсегда
- один и тот же fingerprint может появиться снова после истечения cooldown
- это позволяет слать повторное уведомление, если спустя время на портале остался тот же набор номерков

Настройка cooldown:

- `NOTIFY_COOLDOWN_SECONDS`

---

## 10. Как работает автозапись

Текущий heuristic flow:

1. Открыть сайт
2. Выбрать район
3. Выбрать медорганизацию
4. Выбрать специальность
5. Выбрать врача
6. Открыть расписание
7. Нажать на слот, выбранный по стратегии наблюдения
8. Нажать `Записаться`
9. Попробовать заполнить:
   - ФИО
   - дату рождения
   - email
10. Попробовать нажать кнопку подтверждения
11. Зафиксировать статус:
   - `success`
   - `pending_confirmation`
   - `failed`
   - `unknown`
   - `error`

Это не “идеальная магия”, а production-friendly эвристика с логированием результата. Для реального продакшена после первого живого прогона селекторы и форм-fill лучше довести на фактическом DOM.

---

## 11. Безопасность

### Шифруется

- ФИО
- email
- дата рождения

### Не хранится в открытом виде

- чувствительные персональные поля профиля

### Telegram Mini App

Backend проверяет подпись `initData`.

---

## 12. Переменные окружения

Пример:

```env
APP_NAME=goszdrav-bot
LOG_LEVEL=INFO

BOT_TOKEN=...
BOT_ADMIN_IDS=

DATABASE_URL=postgresql+asyncpg://goszdrav:goszdrav@postgres:5432/goszdrav

GORZDRAV_BASE_URL=https://gorzdrav.spb.ru/service-free-schedule
GORZDRAV_API_BASE_URL=https://gorzdrav.spb.ru/_api/api
SCRAPER_MAX_WORKERS=2
SELENIUM_HEADLESS=true
SELENIUM_TIMEOUT_SECONDS=20
SELENIUM_CHROME_BINARY=
MONITOR_INTERVAL_SECONDS=120
NOTIFY_COOLDOWN_SECONDS=900

MINIAPP_PORT=8080
WEBAPP_BASE_URL=https://your-public-domain.example
WEBAPP_SESSION_TTL_SECONDS=86400
WEBAPP_DEV_MODE=false
WEBAPP_DEV_TELEGRAM_ID=

FIELD_ENCRYPTION_SECRET=...
FIELD_ENCRYPTION_SALT=...
```

### Пояснения

- `BOT_TOKEN` — Telegram bot token
- `DATABASE_URL` — строка подключения к PostgreSQL
- `GORZDRAV_BASE_URL` — базовый URL flow записи
- `GORZDRAV_API_BASE_URL` — backend API Госздрава для каталога и расписаний
- `SCRAPER_MAX_WORKERS` — максимальное число конкурентных Selenium-задач
- `SELENIUM_HEADLESS` — headless режим браузера
- `SELENIUM_TIMEOUT_SECONDS` — timeout ожидания DOM
- `SELENIUM_CHROME_BINARY` — путь к браузеру при ручной настройке
- `MONITOR_INTERVAL_SECONDS` — частота цикла worker-а
- `NOTIFY_COOLDOWN_SECONDS` — антидубль уведомлений
- `MINIAPP_PORT` — порт, на который публикуется FastAPI + Mini App на хост-машине
- `WEBAPP_BASE_URL` — публичный HTTPS URL Mini App
- `WEBAPP_DEV_MODE` — локальный dev-режим Mini App вне Telegram
- `WEBAPP_DEV_TELEGRAM_ID` — Telegram ID, который использовать в локальном dev-режиме
- `FIELD_ENCRYPTION_SECRET` / `FIELD_ENCRYPTION_SALT` — материалы для генерации ключа шифрования

Важно:

- Telegram принимает кнопку `web_app` только для `https://` URL
- `http://localhost:8081` подходит только для проверки страницы в обычном браузере
- если `WEBAPP_BASE_URL` не HTTPS, бот автоматически скрывает кнопку Mini App и остается доступен через chat wizard
- чтобы локальная страница в браузере могла читать и сохранять профиль, включите `WEBAPP_DEV_MODE=true`
- в dev-режиме страница привязывается к `WEBAPP_DEV_TELEGRAM_ID` или к первому ID из `BOT_ADMIN_IDS`

---

## 13. Docker запуск

### Требования

- Docker
- Docker Compose plugin

### Шаги

1. Скопировать `.env.example` в `.env`
2. Заполнить секреты
3. Если `8080` занят на хосте, поменять `MINIAPP_PORT`, например на `8081`
4. Запустить:

```bash
docker compose --env-file .env up --build
```

### Какие сервисы стартуют

- `postgres`
- `migrate`
- `bot`
- `miniapp`
- `worker`

### Порты

- `5432` — PostgreSQL
- `${MINIAPP_PORT}` — FastAPI + Mini App на хосте

### Пример боевого деплоя Mini App за Nginx

Допустим, Mini App будет доступен на:

- `https://gozdravapp.vladivostok2017.sbs`

Рекомендуемая схема:

1. В `.env` на сервере поставить:

```env
MINIAPP_PORT=8095
WEBAPP_BASE_URL=https://gozdravapp.vladivostok2017.sbs
WEBAPP_DEV_MODE=false
```

2. Поднять проект:

```bash
docker compose --env-file .env up -d --build
```

3. Выпустить сертификат для домена и подключить его в Nginx.

4. Проксировать `https://gozdravapp.vladivostok2017.sbs` на `127.0.0.1:8095`.

После этого:

- бот начнет показывать кнопку Mini App в `/start`
- бот поставит Mini App в постоянную кнопку меню Telegram
- fallback через чат останется запасным вариантом

---

## 14. Локальный запуск без Docker

### Требования

- Python `3.12+`
- PostgreSQL
- Chromium или Google Chrome
- ChromeDriver

### Шаги

1. Создать виртуальное окружение
2. Установить зависимости:

```bash
pip install -e .[dev]
```

3. Подготовить `.env`
4. Выполнить миграции:

```bash
alembic upgrade head
```

5. Запустить API:

```bash
python -m goszdrav_bot.api
```

6. В другом терминале запустить бота:

```bash
python -m goszdrav_bot.bot
```

7. В третьем терминале запустить worker:

```bash
python -m goszdrav_bot.workers
```

---

## 15. Как дебажить scraper

Если каталог или автозапись работают нестабильно, первый шаг:

- выставить `SELENIUM_HEADLESS=false`

Потом:

1. Вручную пройти путь на сайте
2. Посмотреть, где DOM отличается от ожидаемого
3. Править `src/goszdrav_bot/scraper/selenium_client.py`

Особенно внимательно смотреть на:

- кнопки `Выбрать`
- блоки расписания
- карточки врача
- элементы календаря
- финальную кнопку `Записаться`
- поля формы подтверждения

---

## 16. Где править код в зависимости от задачи

### Изменился flow сайта

Править:

- `src/goszdrav_bot/scraper/selenium_client.py`

### Изменилась модель профиля

Править:

- `src/goszdrav_bot/db/models.py`
- `src/goszdrav_bot/schemas/profile.py`
- `src/goszdrav_bot/services/profile.py`
- миграции Alembic
- Mini App форму

### Изменилась модель наблюдений

Править:

- `src/goszdrav_bot/db/models.py`
- `src/goszdrav_bot/schemas/watch.py`
- `src/goszdrav_bot/services/watch_targets.py`
- `src/goszdrav_bot/services/monitoring.py`
- `src/goszdrav_bot/api/routes/watch_targets.py`

### Изменился Telegram UX

Править:

- `src/goszdrav_bot/bot/handlers/`
- `src/goszdrav_bot/bot/keyboards/`
- `src/goszdrav_bot/webapp/templates/profile.html`

### Изменились правила уведомлений

Править:

- `src/goszdrav_bot/services/monitoring.py`
- `src/goszdrav_bot/services/watch_targets.py`

---

## 17. Тесты

Сейчас в проекте есть базовые проверки на:

- команды бота
- валидацию профиля
- базовую логику сброса зависимостей профиля
- roundtrip шифрования

Запуск:

```bash
pytest
```

---

## 18. Известные ограничения

Проект уже доведён до рабочей архитектуры, но есть честные ограничения, которые важно понимать команде:

- Selenium-эвристики зависят от текущего DOM портала
- автозапись реализована best-effort, а не через стабильный официальный API
- после первого реального прогона селекторы почти наверняка потребуют 1-2 точечных правок
- при сильных изменениях портала приоритетно чинится `selenium_client.py`

Это не список недоделок, а нормальная зона сопровождения для любого scraping-based проекта.
