"""Тихі години: проміжок локального часу, коли сповіщення не надсилаються."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_RANGE_RE = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")


@dataclass(frozen=True)
class QuietHours:
    start: time
    end: time
    tz: ZoneInfo

    @classmethod
    def parse(cls, spec: str, tz_name: str) -> "QuietHours":
        """'00:00-06:30' або через північ '23:00-07:00'."""
        m = _RANGE_RE.match(spec)
        if not m:
            raise ValueError(f"QUIET_HOURS «{spec}» має бути у форматі ГГ:ХХ-ГГ:ХХ")
        h1, m1, h2, m2 = map(int, m.groups())
        try:
            tz = ZoneInfo(tz_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Невідома TIMEZONE «{tz_name}»") from exc
        return cls(time(h1, m1), time(h2, m2), tz)

    def contains(self, moment: datetime | None = None) -> bool:
        local = (moment or datetime.now(timezone.utc)).astimezone(self.tz).time()
        if self.start <= self.end:
            return self.start <= local < self.end
        return local >= self.start or local < self.end  # проміжок через північ

    def __str__(self) -> str:
        return f"{self.start:%H:%M}-{self.end:%H:%M} {self.tz.key}"
