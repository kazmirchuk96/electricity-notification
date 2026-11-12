# Сповіщення «світло з'явилося» на iPhone

Сервіс читає Telegram-канал СвітлоБота (напр. «Волошкова 2/1»). Коли там з'являється пост
`🟢 18:19 Світло з'явилося`, він надсилає на iPhone гучне сповіщення.

```
Канал СвітлоБота ──▶ Telethon (ваш акаунт) ──▶ парсер ──▶ Bark (critical alert) ──▶ 🔊 iPhone
                                                     └──▶ Telegram-бот (опційно)
```

Чому так: Telegram не вміє ставити окремий звук на повідомлення з певним текстом, а звичайного
бота в чужий канал не додати. Тому канал читає ваш власний акаунт через Telegram API, а звук
дає Bark: його critical alerts звучать навіть у беззвучному режимі та у Focus.

## 1. Підготовка

1. **Telegram API**: на https://my.telegram.org → *API development tools* створіть застосунок,
   скопіюйте `api_id` і `api_hash`.
2. **Bark**: встановіть [Bark](https://apps.apple.com/app/id1403753865) на iPhone, дозвольте
   сповіщення **і Critical Alerts**. Скопіюйте ключ із URL на головному екрані
   (`https://api.day.app/<КЛЮЧ>/...`).
3. *(Опційно)* **Telegram-бот**: створіть бота в @BotFather, напишіть йому `/start`, у чаті з ботом
   поставте окремий гучний звук (Notifications → Sound).

## 2. Встановлення

```bash
cd ~/Projects/electricity-notification
```

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
```

```bash
cp .env.example .env
```

Заповніть у `.env`: `TG_API_ID`, `TG_API_HASH`, `BARK_KEY` (та/або `TG_BOT_TOKEN`).

## 3. Вхід у Telegram і вибір каналу

```bash
.venv/bin/python -m power_notifier login
```

Скрипт попросить номер телефону, код із Telegram і 2FA-пароль (якщо є). Сесія збережеться
у `data/user.session`. Цей файл дає повний доступ до акаунта, тому не передавайте його нікому.

```bash
.venv/bin/python -m power_notifier list-chats Волошкова
```

Скопіюйте id каналу (типу `-100…`) у `TG_CHANNEL` у `.env`.

## 4. Перевірка звуку

```bash
.venv/bin/python -m power_notifier test-notify
```

## 5. Запуск

Вручну:

```bash
.venv/bin/python -m power_notifier
```

Фоном на Mac (автозапуск, перезапуск при падінні):

```bash
./deploy/install-launchd.sh
```

Лог пишеться в `logs/notifier.log`. Видалити сервіс: `./deploy/install-launchd.sh uninstall`.

> ⚠️ Якщо Mac стоїть удома, то поки світла немає, у нього немає й інтернету. Сповіщення прийде,
> коли повернеться роутер (Telethon дотягує пропущені пости). Щоб дізнаватися про світло,
> коли ви не вдома, запускайте сервіс на VPS.

На VPS (Docker):

```bash
docker build -t power-notifier .
```

```bash
docker run -it --rm --env-file .env -v "$PWD/data:/app/data" power-notifier python -m power_notifier login
```

```bash
docker run -d --name power-notifier --restart unless-stopped --env-file .env -v "$PWD/data:/app/data" power-notifier
```

## Налаштування (`.env`)

| Змінна | За замовч. | Опис |
|---|---|---|
| `BARK_SOUND` | `alarm` | звук Bark |
| `BARK_CRITICAL` | `true` | звучить навіть у беззвучному режимі |
| `BARK_VOLUME` | `10` | гучність critical alert, 0–10 |
| `BARK_CALL` | `false` | повторювати звук ~30 с |
| `NOTIFY_ON_OFF` | `false` | також тихе сповіщення, коли світло зникло |
| `MAX_MESSAGE_AGE_MIN` | `30` | пропускати пости, старші за N хв (0 = не пропускати) |

## Тести

```bash
.venv/bin/pip install -r requirements-dev.txt && .venv/bin/pytest
```
