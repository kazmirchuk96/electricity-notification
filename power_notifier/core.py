"""Спільна політика: чи слати сповіщення про подію і як саме. Без I/O Telegram."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from .config import Config, ConfigError
from .notifiers import BarkNotifier, MultiNotifier, TelegramBotNotifier
from .parser import PowerEvent, PowerStatus, format_notification

log = logging.getLogger(__name__)


def should_notify(
    event: PowerEvent,
    posted_at: datetime | None,
    *,
    max_age_min: int,
    notify_on_off: bool,
    now: datetime | None = None,
) -> bool:
    if max_age_min > 0 and posted_at is not None:
        age = (now or datetime.now(timezone.utc)) - posted_at
        if age > timedelta(minutes=max_age_min):
            log.info("Подія %s застара (%s) — пропускаю", event.status.value, age)
            return False
    if event.status is PowerStatus.OFF and not notify_on_off:
        log.info("Світло зникло (%s) — сповіщення вимкнене", event.time)
        return False
    return True


async def deliver(notifier: MultiNotifier, event: PowerEvent) -> bool:
    """Шле сповіщення. True — якщо хоча б один канал доставив."""
    title, body = format_notification(event)
    log.info("Подія: %s — %s", event.status.value, title)
    failed = await notifier.send(title, body, urgent=event.status is PowerStatus.ON)
    return len(failed) < len(notifier.notifiers)


async def build_notifier(cfg: Config, client=None) -> MultiNotifier:
    """Збирає канали сповіщень з конфігу. `client` (Telethon) потрібен лише щоб
    підставити власний id як TG_BOT_CHAT_ID, якщо той не заданий."""
    notifiers = []
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
            raise ConfigError("Задайте TG_BOT_CHAT_ID (ваш числовий id у Telegram) для Telegram-бота")
        notifiers.append(TelegramBotNotifier(cfg.bot_token, chat_id))
    if not notifiers:
        raise ConfigError("Не налаштовано жодного каналу сповіщень: задайте BARK_KEY та/або TG_BOT_TOKEN")
    return MultiNotifier(notifiers)
