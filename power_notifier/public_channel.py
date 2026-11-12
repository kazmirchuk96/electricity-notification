"""Читання публічного каналу через веб-превʼю https://t.me/s/<username> — без входу в акаунт."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

import httpx
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (compatible; power-notifier/1.0)"


class ChannelFetchError(RuntimeError):
    pass


@dataclass(frozen=True)
class Post:
    id: int
    date: datetime | None
    text: str


_USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{3,31}$")


def channel_username(ref: str) -> str:
    """'@name', 't.me/name', 'https://t.me/s/name/123' → 'name'."""
    value = ref.strip()
    value = re.sub(r"^(https?://)?(www\.)?(t|telegram)\.me/", "", value)
    value = value.removeprefix("@").removeprefix("s/")
    value = value.split("/")[0].split("?")[0]
    if not _USERNAME_RE.match(value):
        raise ChannelFetchError(f"TG_CHANNEL «{ref}» не схожий на username публічного каналу")
    return value


def parse_channel_page(html: str) -> list[Post]:
    soup = BeautifulSoup(html, "html.parser")
    posts: list[Post] = []
    for node in soup.select("div.tgme_widget_message[data-post]"):
        try:
            post_id = int(node["data-post"].rsplit("/", 1)[1])
        except (IndexError, ValueError):
            continue
        text_node = node.select_one("div.tgme_widget_message_text.js-message_text")
        text = ""
        if text_node is not None:
            for br in text_node.find_all("br"):
                br.replace_with("\n")
            text = text_node.get_text()
        time_node = node.select_one("a.tgme_widget_message_date time[datetime]")
        date = datetime.fromisoformat(time_node["datetime"]) if time_node else None
        posts.append(Post(id=post_id, date=date, text=text))
    posts.sort(key=lambda p: p.id)
    return posts


async def fetch_public_posts(username: str, *, client: httpx.AsyncClient | None = None) -> list[Post]:
    """Останні ~20 постів каналу, від старших до новіших."""
    own = client is None
    client = client or httpx.AsyncClient(timeout=20, follow_redirects=True, headers={"User-Agent": USER_AGENT})
    try:
        resp = await client.get(f"https://t.me/s/{username}")
        resp.raise_for_status()
    finally:
        if own:
            await client.aclose()
    # Якщо превʼю вимкнене або канал приватний, Telegram редиректить на t.me/<username>.
    if not resp.url.path.startswith("/s/"):
        raise ChannelFetchError(f"У каналу @{username} немає публічного веб-превʼю (t.me/s/{username})")
    posts = parse_channel_page(resp.text)
    if not posts:
        raise ChannelFetchError(f"На t.me/s/{username} не знайдено жодного поста — змінилась верстка?")
    return posts
