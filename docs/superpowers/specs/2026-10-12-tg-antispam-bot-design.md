# Дизайн: Telegram-бот автоматизации сообществ (MVP)

Дата: 2026-10-12
Статус: утверждён к реализации

## 1. Продукт

Бот-автоматизатор для владельцев крупных Telegram-сообществ. В первой версии (MVP)
решает две задачи: **анти-спам/модерация** и **статистика активности**. Монетизация —
подписка через **Telegram Stars**, разграничение функционала по тарифам.

### Целевая аудитория
- Владельцы крипто- и трейдинг-сообществ.
- Администраторы чатов поддержки и брендов.
- Менеджеры закрытых клубов и платных мастермайндов.
- Организаторы локальных сообществ (нетворкинг, фриланс).

### Границы MVP
**Входит:** анти-спам и фильтрация, статистика, тарифы и оплата Telegram Stars,
онбординг владельца, Docker-окружение.
**Не входит (следующие итерации):** приветствие/онбординг новичков, капча-верификация,
автопостинг по расписанию, white-label/API, рефанды, автопродление.

## 2. Архитектура

Подход: **один экземпляр бота, мультитенантная БД** (вариант A). Владельцы добавляют
бота в свои чаты; бот определяет чат по `chat.id` и применяет его настройки и тариф.

```
Telegram API
   │
   ▼
aiogram 3 Dispatcher
   ├─ outer middleware: ChatContext   (найти/создать чат, настройки+тариф, кэш)
   ├─ outer middleware: AntiSpam      (проверка сообщений до хендлеров)
   ├─ inner middleware: StatsCollector(сбор событий в буфер)
   ├─ routers: owner(ЛС) | payments | antispam actions | stats
   └─ background worker (APScheduler): flush_stats, daily_rollup,
                                       cleanup_logs, subscription_lifecycle
        │
        ├──────────────► PostgreSQL (SQLAlchemy 2.0 async + Alembic)
        │
        └──────────────► Redis (состояние флуда/дублей, общее для реплик)
```

### Ключевые решения
- **Кэш настроек в памяти** (`TTLCache`, TTL ~60 сек) — анти-спам middleware не обращается
  к БД на каждое сообщение. После записи в `/settings` вызывается явный
  `ChatContext.invalidate(chat_id)`, чтобы админ видел изменения сразу; TTL — лишь страховка.
- **Состояние флуда/дублей — в Redis** (общее для всех реплик, выживает рестарт процесса).
  Используется один экземпляр в docker-compose; при недоступности Redis — **fail-open**
  (сообщения пропускаются) с записью в лог/метрику, чтобы не блокировать живые чаты.
- **Анти-спам и сбор статистики — в middleware**, вне хендлеров, чтобы правила нельзя
  было обойти.
- **Статистика пишется батчами** из фонового job'а, а не в hot path.
- **Graceful shutdown:** на SIGTERM/SIGINT перехватываем сигнал, останавливаем polling и
  делаем синхронный flush буфера статистики в БД перед выходом.
- **Polling** на старте; переход на webhook позже без изменения бизнес-логики.

### Структура каталогов
```
tg-bot/
├─ docker-compose.yml          # bot + postgres + redis + migrate
├─ Dockerfile
├─ pyproject.toml              # зависимости, ruff, pytest
├─ alembic.ini
├─ .env.example
├─ alembic/versions/
├─ src/app/
│  ├─ main.py                  # entrypoint: bot, dispatcher, scheduler
│  ├─ config.py                # pydantic-settings (.env)
│  ├─ db/base.py               # async engine/session
│  ├─ db/models.py             # SQLAlchemy модели
│  ├─ repositories/            # доступ к данным
│  ├─ state/redis.py           # клиент Redis: state флуда/дублей, TTL-ключи
│  ├─ middlewares/
│  │  ├─ chat_context.py
│  │  ├─ antispam.py
│  │  └─ stats.py
│  ├─ antispam/
│  │  ├─ rules.py              # чистые функции-проверки
│  │  └─ engine.py             # оркестрация правил → действие
│  ├─ handlers/
│  │  ├─ owner/                # /start, /settings
│  │  ├─ payments/             # Stars invoice, pre_checkout, successful_payment
│  │  └─ stats/                # /stats, /top
│  ├─ services/
│  │  ├─ subscriptions.py      # тарифы, лимиты, активация
│  │  ├─ outgoing.py           # очередь исходящих вызовов + rate-limit 25 req/s
│  │  ├─ stats_service.py      # агрегация
│  │  └─ payments/
│  │     ├─ provider.py        # интерфейс PaymentProvider
│  │     └─ stars.py           # реализация Telegram Stars (v1)
│  ├─ keyboards/
│  └─ scheduler/jobs.py
└─ tests/
```

## 3. Модель данных (PostgreSQL)

### Ядро
```
chats
  id BIGINT PK              -- telegram chat_id
  type                      -- group / supergroup / channel
  title TEXT
  owner_id BIGINT           -- telegram user_id владельца
  member_count INT
  is_active BOOL
  created_at, updated_at

chat_admins
  chat_id FK, user_id, role(owner|admin), added_at   PK(chat_id,user_id)

chat_settings
  chat_id PK/FK
  antispam_enabled BOOL
  delete_links BOOL, delete_caps BOOL, delete_duplicates BOOL
  flood_limit SMALLINT
  flood_window_sec SMALLINT
  action violation            -- enum: delete | warn | mute
  warn_limit SMALLINT, mute_minutes SMALLINT
  greeting_text TEXT (nullable, задел на будущее)
  updated_at

stopwords
  id, chat_id FK, word TEXT, added_at    UNIQUE(chat_id, word)
```

### Статистика
```
messages_log                 -- сырые события, retention 30 дней
  id BIGSERIAL, chat_id, user_id, message_id, created_at,
  is_deleted BOOL, violation TEXT NULL

chat_stats_daily             -- агрегат на чат, хранится вечно
  chat_id, date PK       joins INT, leaves INT, messages INT, active_users INT

user_stats_daily             -- агрегат на пользователя (для /top)
  chat_id, user_id, date PK   messages INT, deleted INT
```

### Платежи и тарифы
```
subscriptions
  chat_id PK/FK, plan enum(free|pro|corporate),
  started_at, expires_at, is_active BOOL

transactions
  id BIGSERIAL, chat_id FK, payer_id BIGINT,
  amount_stars INT, payload TEXT,
  telegram_payment_charge_id TEXT UNIQUE, created_at

tier_limits                  -- справочник, заполняется сидом
  plan PK, max_members INT NULL(безлимит), price_stars INT, features JSONB

ownership_claims             -- аудит смены владельца (осиротевшие чаты)
  id BIGSERIAL, chat_id FK, claimant_id BIGINT,
  prev_owner_id BIGINT, created_at
```

### Решения
- `messages_log` чистится ежедневным job'ом (>30 дней), агрегаты остаются — статистика
  хранится бессрочно.
- Тариф привязан к **чату**; платит владелец.
- `member_count` определяет превышение лимита free.
- Агрегация через `INSERT ... ON CONFLICT DO UPDATE` — идемпотентность.

## 4. Движок анти-спама

Два слоя: чистые функции-правила (тестируемы без Telegram) + оркестратор.

### Правила (`antispam/rules.py`)
```
check_links(text, cfg) -> Violation | None       # url, t.me, @username, инвайты
check_caps(text, cfg)  -> Violation | None       # доля заглавных > X и длина > N
check_stopwords(text, matcher) -> Violation | None   # O(len(text)), см. ниже
check_duplicates(state, chat_id, user_id, text, cfg) -> Violation | None
check_flood(state, chat_id, user_id, cfg) -> Violation | None
```
Каждое возвращает `Violation(type, severity)` или `None`.

### Матчинг стоп-слов (Aho-Corasick)
Линейный проход `for word in words: if word in text` даёт `O(N×M)` и убивает CPU на крупных
чатах с большими списками. Поэтому:
- список стоп-слов компилируется в автомат **Aho-Corasick** (`pyahocorasick`, C-расширение);
- автомат **кэшируется по `chat_id`** и инвалидируется при изменении списка (через тот же
  `invalidate`);
- `check_stopwords` = один проход по тексту, `O(len(text) + matches)`.
- Фоллбэк без C-расширения — скомпилированная альтернация `regex` (тоже кэшируется), если
  `pyahocorasick` недоступен.

### Оркестратор (`antispam/engine.py`)
```
engine.evaluate(message, settings, stopwords, state) -> Decision(action, reason)
```
- Порядок проверки: **flood → duplicates → stopwords → links → caps**.
- Первое сработавшее правило → одно решение с действием.
- **Исключения:** админы (`chat_admins`) не проверяются; сервисные сообщения, команды
  `/...`, собственные ответы бота — пропускаются.
- Действия: `delete` → `deleteMessage`; `warn` → удалить + предупреждение + счётчик, при
  `warn_limit` → mute; `mute` → `restrictChatMember(until_date=now+mute_minutes)`.
- Срабатывание логируется в `messages_log(violation=...)`.

### Состояние окна (flood/duplicates)
Хранится в **Redis**, ключи с TTL = `flood_window_sec` (автоочистка без ручного GC):

```
flood:{chat_id}:{user_id}    -> ZADD timestamp (score=ts), ZREMRANGEBYSCORE (окно),
                                ZCARD → счётчик
dup:{chat_id}:{user_id}      -> хэш текст→ts, SETEX на окно; проверка точного повтора
```
- `check_flood`/`check_duplicates` читают и пишут счётчики в Redis — состояние общее для
  всех реплик и переживает рестарт процесса.
- Недоступность Redis → **fail-open**: правило пропускается, событие логируется; модерация
  деградирует мягко, но чат не блокируется.
- Атомарность инкремента — через Lua-скрипт или `MULTI`, чтобы избежать гонок между
  репликами.

### Middleware
`outer middleware` на `Message` и `ChatMemberUpdated`. Настройки — из кэша ChatContext.

## 5. Статистика

### Сбор
- `StatsCollector` кладёт событие в in-memory очередь (без записи в БД на каждое сообщение).
- Job `flush_stats` (каждые ~15 сек или 500 событий): батч-INSERT в `messages_log`,
  батч-UPSERT в `chat_stats_daily` / `user_stats_daily`.
- `joins`/`leaves` — из `ChatMemberUpdated`, объём мал → апсерт сразу.

### Агрегация и ретеншн
- `daily_rollup` в 00:05 — фиксирует итоги дня.
- `cleanup_logs` ежедневно — удаление `messages_log` старше 30 дней.

### Представление
- `/stats`:
  ```
  Сегодня: 1 240 сообщений · 180 активных · +12 / −3
  7 дней: 8 900 сообщений · средний день 1 270 · активных 420
  ```
- `/top [day|week|month]` — топ-10 по сообщениям (+ удалённые).
- `/stats chart` — PNG (matplotlib), **фича Pro-тарифа**.
- Источник: только `*_stats_daily`; сырой лог читают уборщик и live-«сегодня».

## 6. Тарифы и Telegram Stars

| План | Лимит участников | Фичи |
|---|---|---|
| `free` | 1 000 | базовый анти-спам, текстовый `/stats` |
| `pro` | безлимит | графики, кастомные правила/стоп-слова, приоритет |
| `corporate` | безлимит | + white-label, API (задел) |

`price_stars` и `features` — в `tier_limits`, меняются без релиза.

### Провайдеры оплаты
Оплата идёт через интерфейс `PaymentProvider`, чтобы добавить вендора без переписывания
логики тарифов:

```
PaymentProvider:
  create_invoice(chat_id, plan, price) -> invoice
  handle_pre_checkout(query) -> bool
  handle_payment(update) -> PaymentResult   # идемпотентно
```

- **v1: реализация `StarsProvider`** (Telegram Stars, XTR) — самый низкий барьер,
  без юрлица, работает в любой стране.
- **Задел:** `CryptoBotProvider` (USDT/TON) и `StripeProvider` (Web App) — отдельными
  итерациями. Stripe требует юрлица и доступности в стране плательщика; CryptoBot — сторонний
  кастодиальный сервис и не гарантирует API-рекуррент.
- Активация подписки одна для всех провайдеров: идемпотентный upsert в `subscriptions` по
  `telegram_payment_charge_id` (для не-Stars провайдеров — по их `external_payment_id`,
  поле добавляется при реализации).

### Поток оплаты (Stars, v1)
1. `/subscription` в ЛС → инлайн-меню планов.
2. `sendInvoice(currency="XTR", provider_token="", payload="chat_id:plan")`.
3. `pre_checkout_query` → `answer_pre_checkout_query(ok=True)`.
4. `successful_payment` → upsert `subscriptions` (`expires_at = now + 30d`), запись в `transactions`.
5. Идемпотентность: `telegram_payment_charge_id UNIQUE`, `INSERT ... ON CONFLICT DO NOTHING`.

### Лимиты
- Проверка фичи — `subscriptions.has_feature(chat_id, "charts")`.
- Free > 1000 участников: базовый анти-спам сохраняется; pro-фичи отключаются; владельцу
  раз в сутки — уведомление в ЛС о превышении лимита.
- Оплата только владельцем (`role=owner`) из ЛС.

### Жизненный цикл (`subscription_lifecycle`, ежедневно)
- за 3 дня до `expires_at` → напоминание;
- после `expires_at` → `is_active=false`, откат на `free`; статистика сохраняется.

### Claim ownership (осиротевшие чаты)
Если `owner_id` больше не администратор чата (ушёл или снят), чат «осиротеет»: настройки
менять и оплачивать некому.
- Job `subscription_lifecycle` раз в сутки через `getChatAdministrators` помечает чаты,
  где `owner_id` отсутствует среди админов.
- В таком чате действующий админ с правом `can_promote_members` получает кнопку
  «Взять управление»; бот заново проверяет его права через `getChatAdministrators`.
- При успехе: `owner_id` переносится, прежний владелец теряет доступ, факт пишется в
  `ownership_claims` (аудит) и обеим сторонам уходит уведомление.
- Защита от злоупотреблений: claim доступен только админам с правом назначения админов и
  только пока прежний `owner_id` не в админах; повторные claim'ы логируются.

## 7. UX владельца, ошибки, dev/тесты

### ЛС бота — пульт владельца
- `/start` — онбординг, кнопка «Добавить в чат» (`?startgroup=true`), список чатов.
- `/settings` → выбор чата → инлайн-меню: тумблеры, `flood_limit`/`flood_window`,
  `action`, стоп-слова (FSM-ввод), кнопка «Апгрейд».
- `/stats`, `/top`, `/subscription`.
- `set_my_commands` — разные наборы для ЛС и групп.

### Проверка прав бота
При добавлении в чат: `get_chat_member` → есть ли `delete_messages`/`restrict_members`.
Если нет — инструкция владельцу, анти-спам не активируется.

### Ошибки и надёжность
- Retry (tenacity) на `TelegramRetryAfter` и сетевые ошибки.
- **Исходящая очередь с rate-limit:** все вызовы, меняющие состояние
  (`deleteMessage`, `restrictChatMember`, `banChatMember` и т.п.), проходят через
  token-bucket очередь с лимитом **25 req/s** (ниже глобального лимита Telegram ~30 req/s),
  чтобы спам-рейд не упёрся в лимит API. Отправка сообщений учитывает per-chat ~1 msg/s.
  Переполнение очереди → приоритезация модерации, отброс низкоприоритетных задач с логом.
- Глобальный error handler: логирует, не роняет polling.
- Структурированные логи (`structlog`), уровень из `.env`.

### Dev/Docker
```
docker-compose.yml:
  postgres:16
  redis:7
  migrate   — одноразовый init-контейнер: alembic upgrade head, затем exit
  bot       — depends_on: [postgres, redis, migrate(completed)], без миграций в entrypoint
Dockerfile: python:3.12-slim, non-root, entrypoint = python -m app.main
.env.example: BOT_TOKEN, DATABASE_URL, REDIS_URL, LOG_LEVEL, SUPERADMIN_IDS
make: install | migrate | run | test | lint
```
- Миграции только Alembic и только в сервисе `migrate` (не в entrypoint бота), чтобы
  исключить гонку при запуске >1 реплики.
- В compose бот стартует после успешного завершения `migrate`
  (`depends_on: { migrate: { condition: service_completed_successfully } }`).
- Тесты: юнит — правила анти-спама и `subscriptions.has_feature` (state — через
  `fakeredis`); интеграционные — репозитории/апсерты против postgres из compose
  (`pytest`, `pytest-asyncio`).
- Линт/формат — `ruff`. GitHub Actions (lint+test) — опционально.

## 8. Вне границ MVP
- Приветствие/онбординг новичков, капча.
- Автопостинг по расписанию.
- White-label, API-доступ.
- Рефанды (`refundStarPayment`), автопродление.
- Провайдеры оплаты `CryptoBotProvider` / `StripeProvider` (в v1 — только Stars через
  интерфейс `PaymentProvider`).
- Горизонтальное масштабирование (несколько реплик бота): состояние уже в Redis, но
  распределение апдейтов и планировщика между репликами — на будущее.
- Виральный бейдж «Работает на @ВашБот» в приветствии.
