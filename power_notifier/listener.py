"""Telethon-userbot: слухає канал СвітлоБота і шле сповіщення, коли світло з'являється."""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime, timedelta, timezone

from telethon import TelegramClient, events

from .config import Config, ConfigError
from .notifiers import BarkNotifier, MultiNotifier, Notifier, TelegramBotNotifier
from .parser import PowerStatus, format_notification, parse_message

log = logging.getLogger(__name__)


def make_client(cfg: Config) -> TelegramClient:
    cfg.require_telegram()
    cfg.session_path.parent.mkdir(parents=True, exist_ok=True)
    # catch_up: після обриву зв'язку (напр. роутер без світла) дотягує пропущені повідомлення.
    return TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash, catch_up=True)


async def build_notifier(cfg: Config, client: TelegramClient | None = None) -> MultiNotifier:
    notifiers: list[Notifier] = []
    if cfg.bark_key:
        notifiers.append(
            BarkNotifier(
                cfg.bark_key,
                server=cfg.bark_server,
                sound=cfg.bark_sound,
                critical=cfg.bark_critical,
                volume=cfg.bark_volume,
                call=cfg.bark_call,
            )
        )
    if cfg.bot_token:
        chat_id = cfg.bot_chat_id
        if not chat_id and client is not None:
            chat_id = (await client.get_me()).id
        if not chat_id:
            raise ConfigError("Задайте TG_BOT_CHAT_ID або увійдіть у Telegram (login)")
        notifiers.append(TelegramBotNotifier(cfg.bot_token, chat_id))
    if not notifiers:
        raise ConfigError("Не налаштовано жодного каналу сповіщень: задайте BARK_KEY та/або TG_BOT_TOKEN у .env")
    return MultiNotifier(notifiers)


class PowerHandler:
    """Логіка обробки одного повідомлення — окремо від Telethon, щоб легко тестувати."""

    def __init__(self, notifier: MultiNotifier, *, max_age_min: int, notify_on_off: bool) -> None:
        self.notifier = notifier
        self.max_age = timedelta(minutes=max_age_min) if max_age_min > 0 else None
        self.notify_on_off = notify_on_off
        self._seen: deque[int] = deque(maxlen=500)

    async def handle(self, msg_id: int, text: str | None, date: datetime | None) -> bool:
        """Повертає True, якщо сповіщення було відправлено."""
        if msg_id in self._seen:
            return False
        self._seen.append(msg_id)

        event = parse_message(text)
        if event is None:
            log.debug("Повідомлення %s не про світло — пропускаю", msg_id)
            return False

        if self.max_age and date is not None:
            age = datetime.now(timezone.utc) - date
            if age > self.max_age:
                log.info("Повідомлення %s застаре (%s) — пропускаю", msg_id, age)
                return False

        if event.status is PowerStatus.OFF and not self.notify_on_off:
            log.info("Світло зникло (%s) — сповіщення вимкнене", event.time)
            return False

        title, body = format_notification(event)
        log.info("Подія: %s — %s", event.status.value, title)
        failed = await self.notifier.send(title, body, urgent=event.status is PowerStatus.ON)
        return len(failed) < len(self.notifier.notifiers)


async def run(cfg: Config) -> None:
    channel = cfg.require_channel()
    client = make_client(cfg)
    await client.connect()
    if not await client.is_user_authorized():
        raise ConfigError("Сесія не авторизована. Спершу виконайте: python -m power_notifier login")

    entity = await client.get_entity(_channel_ref(channel))
    notifier = await build_notifier(cfg, client)
    handler = PowerHandler(notifier, max_age_min=cfg.max_message_age_min, notify_on_off=cfg.notify_on_off)

    @client.on(events.NewMessage(chats=entity))
    async def _on_message(event: events.NewMessage.Event) -> None:
        try:
            await handler.handle(event.id, event.raw_text, event.date)
        except Exception:  # noqa: BLE001 — слухач не має падати через одне повідомлення
            log.exception("Помилка обробки повідомлення %s", event.id)

    title = getattr(entity, "title", channel)
    log.info("Слухаю «%s». Канали сповіщень: %s", title, ", ".join(n.name for n in notifier.notifiers))
    await client.run_until_disconnected()


def _channel_ref(channel: str) -> str | int:
    """'-100123' → int, інакше рядок (@username / t.me/...)."""
    try:
        return int(channel)
    except ValueError:
        return channel
