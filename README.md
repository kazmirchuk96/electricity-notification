# Сповіщення «світло з'явилося» на iPhone

Сервіс стежить за публічним Telegram-каналом СвітлоБота (напр. «Волошкова 2/1»). Коли там з'являється
пост `🟢 18:19 Світло з'явилося`, він надсилає на iPhone гучне сповіщення.

```
GitHub Actions (cron ~5 хв) ──▶ t.me/s/<канал> ──▶ парсер ──▶ Bark (critical alert) ──▶ 🔊 iPhone
                                                          └──▶ Telegram-бот (опційно)
```

- **Без сервера та без входу в Telegram.** Код працює безкоштовно на GitHub Actions і читає
  публічне веб-превʼю каналу.
- **Bark** — безкоштовний iOS-застосунок. Його critical alerts звучать навіть у беззвучному режимі та у Focus.
- **Затримка.** GitHub запускає cron приблизно кожні 5 хв, але під навантаженням буває 10–20 хв.
  Якщо потрібно за секунди, див. «Режим реального часу (VPS)» нижче.

## 1. iPhone: Bark

1. Встановіть [Bark](https://apps.apple.com/app/id1403753865) і дозвольте сповіщення **та Critical Alerts**.
2. На головному екрані Bark є URL виду `https://api.day.app/<КЛЮЧ>/...`. `<КЛЮЧ>` — це ваш `BARK_KEY`.

*(Опційно)* Telegram-бот: створіть бота в @BotFather, напишіть йому `/start`, у чаті з ботом
поставте окремий гучний звук. Ваш числовий id підкаже @userinfobot.

## 2. GitHub-репозиторій

Репозиторій має бути **публічним**: тоді хвилини Actions безлімітні. Приватному вистачить
лише ~2000 хв/міс, а потрібно ~8600. Секрети в публічному репо не видно, а в логах вони маскуються.

1. Створіть публічний репозиторій і запуште код.
2. *Settings → Secrets and variables → Actions → **Secrets***:
   - `TG_CHANNEL`: username каналу (`@назва` або `https://t.me/назва`)
   - `BARK_KEY`
   - *(опційно)* `TG_BOT_TOKEN`, `TG_BOT_CHAT_ID`
3. *(Опційно)* там само у ***Variables***: `BARK_SOUND`, `BARK_CRITICAL`, `BARK_VOLUME`, `BARK_CALL`, `BARK_REPEAT`,
   `NOTIFY_ON_OFF`, `MAX_MESSAGE_AGE_MIN` (див. таблицю нижче).
4. *(Опційно)* *Actions → Power poller → Run workflow* з галочкою «тестове сповіщення» — перевірка звуку.
5. *Actions → Power poller → Run workflow*: перший ручний запуск. Він запам'ятає останній пост
   (гілка `state`) і далі запускатиметься сам кожні ~5 хв.

Те саме через `gh` (значення секретів команда спитає сама):

```bash
gh repo create electricity-notification --public --source . --push
```

```bash
gh secret set TG_CHANNEL && gh secret set BARK_KEY
```

```bash
gh workflow run poll.yml -f test_notify=true && gh workflow run poll.yml
```

## 3. Перевірка звуку локально

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt && cp .env.example .env
```

Заповніть `BARK_KEY` і `TG_CHANNEL` у `.env`, потім:

```bash
.venv/bin/python -m power_notifier test-notify
```

```bash
.venv/bin/python -m power_notifier poll
```

## Налаштування

| Змінна | За замовч. | Опис |
|---|---|---|
| `BARK_SOUND` | `alarm` | звук Bark |
| `BARK_CRITICAL` | `true` | звучить навіть у беззвучному режимі |
| `BARK_VOLUME` | `10` | гучність critical alert, 0–10 |
| `BARK_CALL` | `false` | повторювати звук ~30 с |
| `BARK_REPEAT` | `1` | скільки разів надіслати сповіщення «з'явилося» (пауза ~4 с) |
| `NOTIFY_ON_OFF` | `false` | також тихе сповіщення, коли світло зникло |
| `MAX_MESSAGE_AGE_MIN` | `120` в Actions, `30` локально | не сповіщати про події, старші за N хв |

Як працює `poll`: з нових постів береться лише **остання** подія. Якщо між двома запусками світло
з'явилось і знову зникло, тривоги «з'явилося» не буде. Якщо сповіщення не вдалося доставити, стан
не оновлюється, і наступний запуск спробує ще раз.

## Обслуговування

- Якщо workflow падає (наприклад, Telegram змінив верстку t.me/s), GitHub надішле лист.
- GitHub вимикає cron у публічних репо після 60 днів без активності. Workflow сам робить keepalive
  кожні ~20 днів. Якщо його все ж вимкнуть, увімкніть одною кнопкою в *Actions*.

## Режим реального часу (VPS)

Опційно, якщо потрібна миттєва реакція і є сервер. `run` слухає канал через ваш Telegram-акаунт
(Telethon), тож потрібні `TG_API_ID`/`TG_API_HASH` з https://my.telegram.org.

```bash
docker build -t power-notifier .
```

```bash
docker run -it --rm --env-file .env -v "$PWD/data:/app/data" power-notifier python -m power_notifier login
```

```bash
docker run -d --name power-notifier --restart unless-stopped --env-file .env -v "$PWD/data:/app/data" power-notifier
```

Файл `data/user.session` дає повний доступ до акаунта, тому не передавайте його нікому.

## Тести

```bash
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest
```
