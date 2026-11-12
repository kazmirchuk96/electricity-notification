"""CLI: python -m power_notifier [run|login|list-chats|test-notify]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from .config import Config, ConfigError
from .listener import build_notifier, make_client, run


async def _login(cfg: Config) -> None:
    client = make_client(cfg)
    await client.start()  # інтерактивно питає номер телефону, код і 2FA-пароль
    me = await client.get_me()
    print(f"✅ Увійшли як {me.first_name} (id {me.id}). Сесія: {cfg.session_path}.session")
    await client.disconnect()


async def _list_chats(cfg: Config, query: str | None) -> None:
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
    client = None
    if cfg.bot_token and not cfg.bot_chat_id:
        client = make_client(cfg)
        await client.connect()
    notifier = await build_notifier(cfg, client)
    failed = await notifier.send("💡 Тест: світло з'явилося", "Так звучатиме сповіщення")
    if client:
        await client.disconnect()
    if failed:
        raise ConfigError(f"Не вдалося доставити через: {', '.join(failed)}")
    print("✅ Тестове сповіщення надіслано: " + ", ".join(n.name for n in notifier.notifiers))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="power_notifier", description="Сповіщення на iPhone, коли з'являється світло")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("run", help="слухати канал (за замовчуванням)")
    sub.add_parser("login", help="одноразовий вхід у Telegram-акаунт")
    lc = sub.add_parser("list-chats", help="показати канали/групи з їх id")
    lc.add_argument("query", nargs="?", help="фільтр за назвою, напр. Волошкова")
    sub.add_parser("test-notify", help="надіслати тестове сповіщення")
    args = parser.parse_args(argv)

    cfg = Config.load()
    logging.basicConfig(
        level=cfg.log_level,
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    logging.getLogger("telethon").setLevel(logging.WARNING)

    cmd = args.cmd or "run"
    try:
        if cmd == "login":
            asyncio.run(_login(cfg))
        elif cmd == "list-chats":
            asyncio.run(_list_chats(cfg, args.query))
        elif cmd == "test-notify":
            asyncio.run(_test_notify(cfg))
        else:
            asyncio.run(run(cfg))
    except ConfigError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
