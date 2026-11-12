"""Режим одноразової перевірки (для GitHub Actions cron).

Кожен запуск: читає t.me/s/<канал>, бере пости новіші за `last_id` зі стану, з них — лише
ОСТАННЮ подію про світло (якщо світло вже встигло зникнути знову, «з'явилося» неактуальне),
шле сповіщення і зберігає новий `last_id`. Якщо доставка не вдалася, стан не просувається —
наступний запуск спробує ще раз.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Awaitable, Callable

from .config import Config
from .core import deliver, should_notify
from .notifiers import MultiNotifier
from .parser import parse_message
from .public_channel import Post, channel_username, fetch_public_posts

log = logging.getLogger(__name__)

Fetcher = Callable[[str], Awaitable[list[Post]]]


@dataclass(frozen=True)
class PollResult:
    state_changed: bool
    notified: bool


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n")


async def poll_once(
    cfg: Config,
    notifier: MultiNotifier,
    *,
    fetch: Fetcher = fetch_public_posts,
    now: datetime | None = None,
) -> PollResult:
    username = channel_username(cfg.require_channel())
    posts = await fetch(username)

    state = load_state(cfg.state_path)
    last_id: int | None = state.get("last_id")
    new_posts = [p for p in posts if last_id is None or p.id > last_id]
    log.info("Постів на сторінці: %d, нових: %d (last_id=%s)", len(posts), len(new_posts), last_id)
    if not new_posts:
        return PollResult(state_changed=False, notified=False)

    notified = False
    events = [(p, ev) for p in new_posts if (ev := parse_message(p.text))]
    if events:
        post, event = events[-1]
        if should_notify(
            event,
            post.date,
            max_age_min=cfg.max_message_age_min,
            notify_on_off=cfg.notify_on_off,
            quiet_hours=cfg.quiet_hours,
            now=now or datetime.now(timezone.utc),
        ):
            notified = await deliver(notifier, event)
            if not notified:
                log.error("Доставка не вдалася — стан не оновлюю, повторю наступного запуску")
                return PollResult(state_changed=False, notified=False)

    state["last_id"] = new_posts[-1].id
    save_state(cfg.state_path, state)
    return PollResult(state_changed=True, notified=notified)
