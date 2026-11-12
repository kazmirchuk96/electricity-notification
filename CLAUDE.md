# CLAUDE.md

Сервіс, який шле гучне push-сповіщення на iPhone, коли в Telegram-каналі СвітлоБота
з'являється пост «🟢 HH:MM Світло з'явилося».

> **Правило:** оновлюй цей файл при кожній серйозній архітектурній зміні (новий канал
> сповіщень, інший спосіб читання Telegram, зміна деплою, нові модулі, зміна формату
> повідомлень бота). Мова документації й повідомлень для користувача — українська.

## Архітектура

```
Telegram-канал ─▶ listener.py (Telethon userbot, events.NewMessage)
                     └▶ PowerHandler.handle(): дедуп за msg id → parse_message() → фільтр віку → фільтр статусу
                          └▶ MultiNotifier (паралельно, 3 спроби з backoff)
                               ├▶ BarkNotifier        (POST {BARK_SERVER}/push, level=critical)
                               └▶ TelegramBotNotifier (Bot API sendMessage)
```

| Файл | Відповідальність |
|---|---|
| `power_notifier/parser.py` | Чистий парсинг тексту → `PowerEvent(status, time, duration, schedule)`; `format_notification()`. Без I/O. |
| `power_notifier/notifiers.py` | Канали доставки. Протокол `Notifier.send(title, body, *, urgent)`. `MultiNotifier` повертає список каналів, що не спрацювали. |
| `power_notifier/listener.py` | Telethon-клієнт, збирання нотифаєрів з конфігу, `PowerHandler` (логіка без Telethon, тестується окремо), `run()`. |
| `power_notifier/config.py` | `Config.load()` з `.env` (python-dotenv). `ConfigError` → CLI показує повідомлення і виходить з кодом 2. |
| `power_notifier/__main__.py` | CLI: `run` (дефолт), `login`, `list-chats [query]`, `test-notify`. |
| `deploy/install-launchd.sh` | Фоновий сервіс macOS (KeepAlive), лог у `logs/notifier.log`. |
| `Dockerfile` | Деплой на VPS; `.env` через `--env-file`, сесія в томі `/app/data`. |

## Ключові рішення

- **Userbot, а не бот**: звичайного бота в чужий канал не додати, тож читаємо через акаунт
  користувача (Telethon, `api_id`/`api_hash`). Сесія — `data/user.session` (gitignored, секрет).
- **Bark як основний канал**: тільки critical alert гарантує звук у беззвучному режимі/Focus.
  Telegram-бот — запасний варіант; якщо `TG_BOT_CHAT_ID` порожній, береться `get_me().id`.
- **`catch_up=True` + `MAX_MESSAGE_AGE_MIN`**: після обриву мережі (роутер без світла) пропущені
  пости дотягуються, але занадто старі не викликають тривогу. Дедуп за id: deque на 500.
- Сповіщення про «світло зникло» вимкнені за замовчуванням (`NOTIFY_ON_OFF`), а коли ввімкнені,
  йдуть як `urgent=False` (Bark `passive`, Telegram `disable_notification`).
- Парсер не залежить від заголовка «СвітлоБот ⚡ …» і терпить різні апострофи (`' ’ ʼ \``).

## Розробка

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest            # asyncio_mode=auto (pytest.ini)
.venv/bin/python -m power_notifier --help
```

- Нові формати повідомлень бота: спершу додай приклад у `tests/test_parser.py`, потім змінюй regex.
- Новий канал сповіщень: клас із `name` і `async send(title, body, *, urgent)` у `notifiers.py`,
  підключення в `listener.build_notifier()`, змінні в `.env.example`, README та цей файл.
- Ніколи не коміть `.env`, `data/*.session`, `logs/`.
