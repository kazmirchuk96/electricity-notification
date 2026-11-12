"""Розбір повідомлень СвітлоБота.

Приклади тексту (без форматування, як його віддає Telethon `raw_text`):

    🟢 18:19 Світло з'явилося
    🕓 Його не було 7год 5хв
    🗓 Наступне планове: 21:30 - 00:00

    🔴 11:13 Світло зникло
    🕓 Воно було 5год 51хв
    🗓 Очікуємо за розкладом о 17:30
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum


class PowerStatus(str, Enum):
    ON = "on"
    OFF = "off"


@dataclass(frozen=True)
class PowerEvent:
    status: PowerStatus
    time: str | None = None  # "18:19"
    duration: str | None = None  # "7год 5хв" — скільки тривав попередній стан
    schedule: str | None = None  # "21:30 - 00:00" / "17:30"


# Апостроф у "з'явилося" буває різним: ' ’ ʼ ` або взагалі відсутній.
_APOS = "['’ʼ`´]?"
_ON_RE = re.compile(rf"світло\s+з{_APOS}явил[оа]ся", re.IGNORECASE)
_OFF_RE = re.compile(r"світло\s+зникл[оа]", re.IGNORECASE)
_TIME_RE = re.compile(r"\b(\d{1,2}:\d{2})\b")
_DURATION_RE = re.compile(
    r"(?:не\s+було|було)\s+((?:\d+\s*(?:д|дн|год|г|хв|м)\.?\s*)+)", re.IGNORECASE
)
_SCHEDULE_RE = re.compile(
    r"(?:наступне\s+планове|очікуємо(?:\s+за\s+розкладом)?)\s*:?\s*(?:о\s+)?(.+)$",
    re.IGNORECASE,
)


def parse_message(text: str | None) -> PowerEvent | None:
    """Повертає PowerEvent, якщо повідомлення — про зміну стану світла, інакше None."""
    if not text:
        return None

    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    if not lines:
        return None

    status: PowerStatus | None = None
    status_line = ""
    for line in lines:
        if _ON_RE.search(line):
            status, status_line = PowerStatus.ON, line
            break
        if _OFF_RE.search(line):
            status, status_line = PowerStatus.OFF, line
            break
    if status is None:
        return None

    time_match = _TIME_RE.search(status_line)

    duration = None
    schedule = None
    for line in lines:
        if duration is None and (m := _DURATION_RE.search(line)):
            duration = m.group(1).strip()
        if schedule is None and (m := _SCHEDULE_RE.search(line)):
            schedule = m.group(1).strip()

    return PowerEvent(
        status=status,
        time=time_match.group(1) if time_match else None,
        duration=duration,
        schedule=schedule,
    )


def format_notification(event: PowerEvent) -> tuple[str, str]:
    """(title, body) для push-сповіщення."""
    if event.status is PowerStatus.ON:
        title = "💡 Світло з'явилося"
        parts = []
        if event.time:
            title += f" о {event.time}"
        if event.duration:
            parts.append(f"Не було {event.duration}")
        if event.schedule:
            parts.append(f"Наступне планове: {event.schedule}")
    else:
        title = "🔴 Світло зникло"
        parts = []
        if event.time:
            title += f" о {event.time}"
        if event.duration:
            parts.append(f"Було {event.duration}")
        if event.schedule:
            parts.append(f"Очікуємо: {event.schedule}")
    return title, "\n".join(parts) or title
