"""CLI: python -m power_notifier [poll|run|login|list-chats|test-notify]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import Config, ConfigError
from .core import build_notifier
from .public_channel import ChannelFetchError


async def _poll(cfg: Config) -> None:
    from .poller import poll_once

    await poll_once(cfg, await build_notifier(cfg))


async def _run(cfg: Config) -> None:
    from .listener import run

    await run(cfg)


async def _login(cfg: Config) -> None:
    from .listener import make_client

    client = make_client(cfg)
    await client.start()  # інтерактивно питає номер телефону, код і 2FA-пароль
    me = await client.get_me()
    print(f"✅ Увійшли як {me.first_name} (id {me.id}). Сесія: {cfg.session_path}.session")
    await client.disconnect()


async def _list_chats(cfg: Config, query: str | None) -> None:
    from .listener import make_client

    client = make_client(cfg)
    await client.connect()
    if not await client.is_user_authorized():
        raise ConfigError("Спершу виконайте: python -m power_notifier login")
    async for dialog in client.iter_dialogs():
        if not (dialog.is_channel or dialog.is_group):
            continue
        if query and query.lower() not in (dialog.name or "").lower():
            continue
        username = getattr(dialog.entity, "username", None)
        print(f"{dialog.id:>16}  {'@' + username if username else '':<24} {dialog.name}")
    await client.disconnect()


async def _test_notify(cfg: Config) -> None:
    notifier = await build_notifier(cfg)
    failed = await notifier.send("💡 Тест: світло з'явилося", "Так звучатиме сповіщення")
    if failed:
        raise ConfigError(f"Не вдалося доставити через: {', '.join(failed)}")
    print("✅ Тестове сповіщення надіслано: " + ", ".join(n.name for n in notifier.notifiers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="power_notifier", description="Сповіщення на iPhone, коли з'являється світло")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("poll", help="одноразова перевірка публічного каналу (GitHub Actions; за замовчуванням)")
    sub.add_parser("run", help="постійно слухати канал через Telegram-акаунт (VPS)")
    sub.add_parser("login", help="одноразовий вхід у Telegram-акаунт (для run)")
    lc = sub.add_parser("list-chats", help="показати канали/групи з їх id (для run)")
    lc.add_argument("query", nargs="?", help="фільтр за назвою, напр. Волошкова")
    sub.add_parser("test-notify", help="надіслати тестове сповіщення")
    args = parser.parse_args(argv)

    cfg = Config.load()
    logging.basicConfig(level=cfg.log_level, format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    for noisy in ("telethon", "httpx", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    commands = {
        "poll": lambda: _poll(cfg),
        "run": lambda: _run(cfg),
        "login": lambda: _login(cfg),
        "list-chats": lambda: _list_chats(cfg, args.query),
        "test-notify": lambda: _test_notify(cfg),
    }
    try:
        asyncio.run(commands[args.cmd or "poll"]())
    except (ConfigError, ChannelFetchError) as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
