# CLAUDE.md

Сервіс, який шле гучне push-сповіщення на iPhone, коли в публічному Telegram-каналі СвітлоБота
з'являється пост «🟢 HH:MM Світло з'явилося».

> **Правило:** оновлюй цей файл при кожній серйозній архітектурній зміні (новий канал
> сповіщень, інший спосіб читання Telegram, зміна хостингу/деплою, нові модулі, зміна формату
> повідомлень бота). Мова документації й повідомлень для користувача — українська.

## Хостинг (рішення користувача)

- **Mac не варіант** — сервіс не має залежати від комп'ютера користувача.
- **Основний режим — GitHub Actions** (`.github/workflows/poll.yml`): cron `*/5`, команда `poll`.
  Репозиторій має бути **публічним** (безлімітні хвилини; приватному не вистачить 2000 хв/міс).
  Через це в логах не можна друкувати назву каналу чи інші приватні дані — `TG_CHANNEL` є секретом.
- Канал **публічний** → читаємо веб-превʼю `https://t.me/s/<username>` без входу в акаунт.
- Запасний режим реального часу `run` (Telethon userbot) — лише для VPS через Docker.

## Архітектура

```
poll (GitHub Actions)                         run (VPS, Telethon)
  public_channel.fetch_public_posts()           listener: events.NewMessage
  → poller.poll_once(): нові пости > last_id     → PowerHandler.handle(): дедуп за msg id
    → остання подія серед нових                    │
         └──────────────┬─────────────────────────┘
                        ▼
        core.should_notify()  (вік події, статус ON/OFF)
        core.deliver() → MultiNotifier (паралельно, 3 спроби з backoff)
                           ├▶ BarkNotifier        (POST {BARK_SERVER}/push, level=critical)
                           └▶ TelegramBotNotifier (Bot API sendMessage)
```

| Файл | Відповідальність |
|---|---|
| `power_notifier/parser.py` | Чистий парсинг тексту → `PowerEvent(status, time, duration, schedule)`; `format_notification()`. Без I/O. |
| `power_notifier/public_channel.py` | `channel_username()`, `parse_channel_page()` (BeautifulSoup, `div.tgme_widget_message[data-post]`), `fetch_public_posts()`; `ChannelFetchError`, якщо превʼю немає (редирект з `/s/`). |
| `power_notifier/poller.py` | `poll_once()` + JSON-стан `{"last_id": N}` у `STATE_FILE`. |
| `power_notifier/quiet.py` | `QuietHours.parse('00:00-06:30', 'Europe/Kyiv')`, `.contains(now)`; підтримує проміжок через північ. |
| `power_notifier/core.py` | Спільна політика `should_notify()`, `deliver()`, `build_notifier()` з конфігу. |
| `power_notifier/notifiers.py` | Канали доставки. Протокол `Notifier.send(title, body, *, urgent)`. `MultiNotifier` повертає список каналів, що не спрацювали. |
| `power_notifier/listener.py` | Режим `run`: Telethon-клієнт, `PowerHandler`. Telethon імпортується лише тут (у `__main__` — ліниво). |
| `power_notifier/config.py` | `Config.load()` з `.env`/env vars. `ConfigError` → CLI виходить з кодом 2. |
| `power_notifier/__main__.py` | CLI: `poll` (дефолт), `run`, `login`, `list-chats [query]`, `test-notify`. |
| `.github/workflows/poll.yml` | Cron-запуск `poll`; стан у гілці `state` (окремий git init у `./state`, пуш через `github.token`); keepalive кожні ~20 днів. |
| `Dockerfile` | Режим `run` на VPS; `.env` через `--env-file`, сесія в томі `/app/data`. |

## Ключові рішення

- **Тільки остання подія** серед нових постів у `poll`: якщо світло з'явилось і знову зникло між
  запусками cron, тривоги «з'явилося» немає.
- **Стан не просувається при невдалій доставці** — наступний запуск повторить. Перший запуск без
  стану ініціалізує `last_id`; старі події відсікає `MAX_MESSAGE_AGE_MIN` (в Actions за замовч. 120,
  бо cron GitHub запізнюється на 5–20 хв).
- **Стан у гілці `state`**, а не в `main` — щоб бот не засмічував історію коду; concurrency group
  у workflow не дає двом запускам пушити одночасно.
- **Bark як основний канал**: тільки critical alert гарантує звук у беззвучному режимі/Focus.
  Telegram-бот — запасний; у `poll` потрібен явний `TG_BOT_CHAT_ID`.
  У JSON для Bark усі значення — рядки (`volume: "10"`): числове `volume` сервер ігнорує → critical
  alert з гучністю 0, тобто без звуку (перевірено на практиці).
  Bark не вміє програти звук N разів, тому `BARK_REPEAT` шле N окремих push з паузою ~4 с
  (лише для термінових; помилка повтору лише логується).
- **Тихі години** (`QUIET_HOURS`, `TIMEZONE`, модуль `quiet.py`) перевіряються в `should_notify()` за
  поточним часом: подія в тихі години пропускається остаточно (стан просувається), `test-notify` їх ігнорує.
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
- Зміна верстки t.me/s: онови фікстуру `PAGE` у `tests/test_poller.py` за реальною сторінкою.
- Новий канал сповіщень: клас із `name` і `async send(title, body, *, urgent)` у `notifiers.py`,
  підключення в `core.build_notifier()`, змінні в `.env.example`, workflow, README та цей файл.
- Ніколи не коміть `.env`, `data/*.session`, `data/state.json`, `logs/`.
