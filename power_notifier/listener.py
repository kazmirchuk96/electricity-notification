"""Режим реального часу (для VPS): Telethon-userbot слухає канал і шле сповіщення миттєво.

Потрібен вхід у Telegram-акаунт (`login`). Для GitHub Actions використовується `poller.py`.
"""

from __future__ import annotations

import logging
from collections import deque
from datetime import datetime

from telethon import TelegramClient, events

from .config import Config, ConfigError
from .core import build_notifier, deliver, should_notify
from .notifiers import MultiNotifier
from .parser import parse_message
from .quiet import QuietHours

log = logging.getLogger(__name__)


def make_client(cfg: Config) -> TelegramClient:
    cfg.require_telegram()
    cfg.session_path.parent.mkdir(parents=True, exist_ok=True)
    # catch_up: після обриву зв'язку дотягує пропущені повідомлення.
    return TelegramClient(str(cfg.session_path), cfg.api_id, cfg.api_hash, catch_up=True)


class PowerHandler:
    """Обробка одного повідомлення — окремо від Telethon, щоб легко тестувати."""

    def __init__(
        self,
        notifier: MultiNotifier,
        *,
        max_age_min: int,
        notify_on_off: bool,
        quiet_hours: QuietHours | None = None,
    ) -> None:
        self.notifier = notifier
        self.max_age_min = max_age_min
        self.notify_on_off = notify_on_off
        self.quiet_hours = quiet_hours
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
        if not should_notify(
            event,
            date,
            max_age_min=self.max_age_min,
            notify_on_off=self.notify_on_off,
            quiet_hours=self.quiet_hours,
        ):
            return False
        return await deliver(self.notifier, event)


async def run(cfg: Config) -> None:
    channel = cfg.require_channel()
    client = make_client(cfg)
    await client.connect()
    if not await client.is_user_authorized():
        raise ConfigError("Сесія не авторизована. Спершу виконайте: python -m power_notifier login")

    entity = await client.get_entity(_channel_ref(channel))
    notifier = await build_notifier(cfg, client)
    handler = PowerHandler(
        notifier,
        max_age_min=cfg.max_message_age_min,
        notify_on_off=cfg.notify_on_off,
        quiet_hours=cfg.quiet_hours,
    )

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
