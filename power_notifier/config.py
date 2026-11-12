from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from .quiet import QuietHours

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on", "так"}


def _str(name: str, default: str | None = None) -> str | None:
    raw = os.getenv(name)
    return raw.strip() if raw and raw.strip() else default


def _int(name: str, default: int) -> int:
    raw = _str(name)
    return int(raw) if raw is not None else default


def _path(name: str, default: str) -> Path:
    path = Path(_str(name, default))
    return path if path.is_absolute() else PROJECT_ROOT / path


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Config:
    api_id: int | None
    api_hash: str | None
    channel: str | None
    session_path: Path
    state_path: Path

    bark_key: str | None
    bark_server: str
    bark_sound: str
    bark_critical: bool
    bark_volume: int
    bark_call: bool
    bark_repeat: int

    bot_token: str | None
    bot_chat_id: str | None

    max_message_age_min: int
    notify_on_off: bool
    quiet_hours: QuietHours | None
    log_level: str

    @classmethod
    def load(cls, env_file: Path | None = None) -> "Config":
        load_dotenv(env_file or PROJECT_ROOT / ".env")
        api_id = _str("TG_API_ID")
        quiet_spec = _str("QUIET_HOURS")
        try:
            quiet = QuietHours.parse(quiet_spec, _str("TIMEZONE", "Europe/Kyiv")) if quiet_spec else None
        except ValueError as exc:
            raise ConfigError(str(exc)) from exc
        session = _path("TG_SESSION", "data/user")
        state = _path("STATE_FILE", "data/state.json")
        return cls(
            api_id=int(api_id) if api_id else None,
            api_hash=_str("TG_API_HASH"),
            channel=_str("TG_CHANNEL"),
            session_path=session,
            state_path=state,
            bark_key=_str("BARK_KEY"),
            bark_server=_str("BARK_SERVER", "https://api.day.app").rstrip("/"),
            bark_sound=_str("BARK_SOUND", "alarm"),
            bark_critical=_bool("BARK_CRITICAL", True),
            bark_volume=_int("BARK_VOLUME", 10),
            bark_call=_bool("BARK_CALL", False),
            bark_repeat=_int("BARK_REPEAT", 1),
            bot_token=_str("TG_BOT_TOKEN"),
            bot_chat_id=_str("TG_BOT_CHAT_ID"),
            max_message_age_min=_int("MAX_MESSAGE_AGE_MIN", 30),
            notify_on_off=_bool("NOTIFY_ON_OFF", False),
            quiet_hours=quiet,
            log_level=_str("LOG_LEVEL", "INFO").upper(),
        )

    def require_telegram(self) -> None:
        missing = [n for n, v in (("TG_API_ID", self.api_id), ("TG_API_HASH", self.api_hash)) if not v]
        if missing:
            raise ConfigError(f"Не задано в .env: {', '.join(missing)}")

    def require_channel(self) -> str:
        if not self.channel:
            raise ConfigError("Не задано TG_CHANNEL у .env (див. `python -m power_notifier list-chats`)")
        return self.channel
