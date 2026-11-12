from dataclasses import replace
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from power_notifier.config import Config
from power_notifier.notifiers import MultiNotifier
from power_notifier.poller import load_state, poll_once, save_state
from power_notifier.public_channel import (
    ChannelFetchError,
    Post,
    channel_username,
    fetch_public_posts,
    parse_channel_page,
)

# Фрагмент верстки t.me/s/<channel> (структура як у реальної сторінки).
PAGE = """
<div class="tgme_widget_message_wrap js-widget_message_wrap">
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="svitlo_test/101" data-view="x">
  <div class="tgme_widget_message_text js-message_text" dir="auto"><i class="emoji" style="background-image:url('//telegram.org/img/emoji/40/F09F94B4.png')"><b>🔴</b></i> <b>11:13 Світло зникло</b><br/><i class="emoji"><b>🕓</b></i> Воно було 5год 51хв<br/><i class="emoji"><b>🗓</b></i> Очікуємо за розкладом о <b>17:30</b></div>
  <a class="tgme_widget_message_date" href="https://t.me/svitlo_test/101"><time datetime="2026-11-12T09:13:05+00:00" class="time">11:13</time></a>
</div></div>
<div class="tgme_widget_message_wrap js-widget_message_wrap">
<div class="tgme_widget_message text_not_supported_wrap js-widget_message" data-post="svitlo_test/102" data-view="x">
  <div class="tgme_widget_message_text js-message_text" dir="auto"><i class="emoji"><b>🟢</b></i> <b>18:19 Світло з&#39;явилося</b><br/><i class="emoji"><b>🕓</b></i> Його не було 7год 5хв<br/><i class="emoji"><b>🗓</b></i> Наступне планове: <b>21:30 - 00:00</b></div>
  <a class="tgme_widget_message_date" href="https://t.me/svitlo_test/102"><time datetime="2026-11-12T16:19:02+00:00" class="time">18:19</time></a>
</div></div>
"""

T_ON = datetime(2026, 11, 12, 16, 19, 2, tzinfo=timezone.utc)
T_OFF = datetime(2026, 11, 12, 9, 13, 5, tzinfo=timezone.utc)
ON = "🟢 18:19 Світло з'явилося\n🕓 Його не було 7год 5хв"
OFF = "🔴 19:00 Світло зникло"


def test_parse_channel_page():
    posts = parse_channel_page(PAGE)
    assert [p.id for p in posts] == [101, 102]
    assert posts[1].date == T_ON
    assert posts[1].text == "🟢 18:19 Світло з'явилося\n🕓 Його не було 7год 5хв\n🗓 Наступне планове: 21:30 - 00:00"


@pytest.mark.parametrize(
    "ref", ["svitlo_test", "@svitlo_test", "t.me/svitlo_test", "https://t.me/svitlo_test", "https://t.me/s/svitlo_test/102"]
)
def test_channel_username(ref):
    assert channel_username(ref) == "svitlo_test"


def test_channel_username_rejects_invite_link():
    with pytest.raises(ChannelFetchError):
        channel_username("https://t.me/+AbCdEf123")


async def test_fetch_detects_missing_preview():
    def handler(request):
        if request.url.path.startswith("/s/"):
            return httpx.Response(302, headers={"Location": "https://t.me/svitlo_test"})
        return httpx.Response(200, text="<html></html>")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler), follow_redirects=True)
    with pytest.raises(ChannelFetchError, match="превʼю"):
        await fetch_public_posts("svitlo_test", client=client)


async def test_fetch_ok():
    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, text=PAGE)))
    posts = await fetch_public_posts("svitlo_test", client=client)
    assert [p.id for p in posts] == [101, 102]


# ---------- poll_once ----------


class FakeNotifier:
    name = "fake"

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    async def send(self, title, body, *, urgent=True):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append((title, urgent))


@pytest.fixture
def cfg(tmp_path):
    base = Config.load(env_file=tmp_path / "missing.env")
    return replace(
        base, channel="svitlo_test", state_path=tmp_path / "state.json", max_message_age_min=120, notify_on_off=False
    )


def fetcher(*posts):
    async def fetch(username):
        assert username == "svitlo_test"
        return list(posts)

    return fetch


def multi(fake):
    return MultiNotifier([fake], retries=1, backoff=0)


async def test_poll_notifies_new_power_on(cfg):
    save_state(cfg.state_path, {"last_id": 101})
    fake = FakeNotifier()
    res = await poll_once(cfg, multi(fake), fetch=fetcher(Post(101, T_OFF, OFF), Post(102, T_ON, ON)),
                          now=T_ON + timedelta(minutes=7))
    assert res.notified and res.state_changed
    assert fake.calls == [("💡 Світло з'явилося о 18:19", True)]
    assert load_state(cfg.state_path) == {"last_id": 102}


async def test_poll_nothing_new(cfg):
    save_state(cfg.state_path, {"last_id": 102})
    fake = FakeNotifier()
    res = await poll_once(cfg, multi(fake), fetch=fetcher(Post(102, T_ON, ON)), now=T_ON)
    assert not res.state_changed and fake.calls == []


async def test_poll_only_latest_event_counts(cfg):
    """Світло з'явилось і знову зникло між запусками — «з'явилося» вже неактуальне."""
    save_state(cfg.state_path, {"last_id": 100})
    fake = FakeNotifier()
    later = T_ON + timedelta(minutes=30)
    res = await poll_once(cfg, multi(fake), fetch=fetcher(Post(102, T_ON, ON), Post(103, later, OFF)), now=later)
    assert fake.calls == [] and res.state_changed
    assert load_state(cfg.state_path) == {"last_id": 103}


async def test_poll_non_power_post_after_on_still_notifies(cfg):
    save_state(cfg.state_path, {"last_id": 101})
    fake = FakeNotifier()
    res = await poll_once(cfg, multi(fake), fetch=fetcher(Post(102, T_ON, ON), Post(103, T_ON, "Графік на завтра")),
                          now=T_ON)
    assert res.notified and load_state(cfg.state_path) == {"last_id": 103}


async def test_poll_first_run_respects_age(cfg):
    """Без стану: стара подія не викликає тривогу, але стан ініціалізується."""
    fake = FakeNotifier()
    res = await poll_once(cfg, multi(fake), fetch=fetcher(Post(102, T_ON, ON)), now=T_ON + timedelta(hours=5))
    assert fake.calls == [] and load_state(cfg.state_path) == {"last_id": 102}
    assert res.state_changed


async def test_poll_failed_delivery_keeps_state(cfg):
    save_state(cfg.state_path, {"last_id": 101})
    res = await poll_once(cfg, multi(FakeNotifier(fail=True)), fetch=fetcher(Post(102, T_ON, ON)), now=T_ON)
    assert not res.state_changed and load_state(cfg.state_path) == {"last_id": 101}
