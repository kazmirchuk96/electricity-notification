"""Канали доставки сповіщень на iPhone."""

from __future__ import annotations

import asyncio
import logging
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class Notifier(Protocol):
    name: str

    async def send(self, title: str, body: str, *, urgent: bool = True) -> None: ...


class BarkNotifier:
    """Bark (iOS) — підтримує critical alerts, які звучать навіть у беззвучному режимі."""

    name = "bark"

    def __init__(
        self,
        key: str,
        *,
        server: str = "https://api.day.app",
        sound: str = "alarm",
        critical: bool = True,
        volume: int = 10,
        call: bool = False,
        repeat: int = 1,
        repeat_interval: float = 4.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.key = key
        self.server = server.rstrip("/")
        self.sound = sound
        self.critical = critical
        self.volume = max(0, min(10, volume))
        self.call = call
        self.repeat = max(1, repeat)
        self.repeat_interval = repeat_interval
        self._client = client

    def payload(self, title: str, body: str, *, urgent: bool) -> dict:
        data: dict = {
            "device_key": self.key,
            "title": title,
            "body": body,
            "group": "Світло",
        }
        if urgent:
            data["sound"] = self.sound
            if self.critical:
                data["level"] = "critical"
                data["volume"] = self.volume
            else:
                data["level"] = "timeSensitive"
            if self.call:
                data["call"] = "1"
        else:
            data["level"] = "passive"
        return data

    async def send(self, title: str, body: str, *, urgent: bool = True) -> None:
        """Термінові сповіщення шле `repeat` разів (кожне — окремий звук) з паузою між ними."""
        times = self.repeat if urgent else 1
        payload = self.payload(title, body, urgent=urgent)
        async with _client_ctx(self._client) as client:
            await self._post(client, payload)  # помилка першого → MultiNotifier повторить
            for i in range(2, times + 1):
                await asyncio.sleep(self.repeat_interval)
                try:
                    await self._post(client, payload)
                except Exception as exc:  # noqa: BLE001 — головне вже доставлено
                    log.warning("bark: повтор %d/%d не вдався: %s", i, times, exc)

    async def _post(self, client: httpx.AsyncClient, payload: dict) -> None:
        resp = await client.post(f"{self.server}/push", json=payload)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200:
            raise RuntimeError(f"Bark error: {data}")


class TelegramBotNotifier:
    """Повідомлення від власного бота. Окремий звук ставиться в налаштуваннях чату з ботом."""

    name = "telegram-bot"

    def __init__(self, token: str, chat_id: str | int, *, client: httpx.AsyncClient | None = None) -> None:
        self.token = token
        self.chat_id = chat_id
        self._client = client

    async def send(self, title: str, body: str, *, urgent: bool = True) -> None:
        text = title if body == title else f"{title}\n{body}"
        async with _client_ctx(self._client) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{self.token}/sendMessage",
                json={"chat_id": self.chat_id, "text": text, "disable_notification": not urgent},
            )
            data = resp.json()
            if not data.get("ok"):
                raise RuntimeError(f"Telegram Bot API error: {data.get('description', data)}")


class MultiNotifier:
    """Розсилає в усі канали; помилка одного не блокує інші. Кілька спроб з backoff."""

    name = "multi"

    def __init__(self, notifiers: list[Notifier], *, retries: int = 3, backoff: float = 2.0) -> None:
        if not notifiers:
            raise ValueError("Не налаштовано жодного каналу сповіщень (BARK_KEY або TG_BOT_TOKEN)")
        self.notifiers = notifiers
        self.retries = retries
        self.backoff = backoff

    async def send(self, title: str, body: str, *, urgent: bool = True) -> list[str]:
        """Повертає імена каналів, у які доставити не вдалося."""
        results = await asyncio.gather(*(self._send_one(n, title, body, urgent) for n in self.notifiers))
        return [n.name for n, ok in zip(self.notifiers, results) if not ok]

    async def _send_one(self, notifier: Notifier, title: str, body: str, urgent: bool) -> bool:
        for attempt in range(1, self.retries + 1):
            try:
                await notifier.send(title, body, urgent=urgent)
                log.info("Сповіщення надіслано через %s", notifier.name)
                return True
            except Exception as exc:  # noqa: BLE001 — логуємо і пробуємо ще
                log.warning("%s: спроба %d/%d не вдалася: %s", notifier.name, attempt, self.retries, exc)
                if attempt < self.retries:
                    await asyncio.sleep(self.backoff * attempt)
        log.error("%s: сповіщення не доставлено", notifier.name)
        return False


class _client_ctx:
    """Використовує переданий httpx-клієнт (тести) або створює тимчасовий."""

    def __init__(self, client: httpx.AsyncClient | None) -> None:
        self._external = client
        self._owned: httpx.AsyncClient | None = None

    async def __aenter__(self) -> httpx.AsyncClient:
        if self._external is not None:
            return self._external
        self._owned = httpx.AsyncClient(timeout=15)
        return self._owned

    async def __aexit__(self, *exc) -> None:
        if self._owned is not None:
            await self._owned.aclose()
