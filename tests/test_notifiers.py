import json
from datetime import datetime, timedelta, timezone

import httpx

from power_notifier.listener import PowerHandler
from power_notifier.notifiers import BarkNotifier, MultiNotifier, TelegramBotNotifier

ON_MSG = "🟢 18:19 Світло з'явилося\n🕓 Його не було 7год 5хв"
OFF_MSG = "🔴 11:13 Світло зникло\n🕓 Воно було 5год 51хв"


def _mock_client(captured: list, response: dict) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=response)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


async def test_bark_critical_payload():
    captured = []
    n = BarkNotifier("KEY", client=_mock_client(captured, {"code": 200}))
    await n.send("T", "B")
    url, body = captured[0]
    assert url == "https://api.day.app/push"
    assert body["device_key"] == "KEY"
    assert body["level"] == "critical" and body["volume"] == 10 and body["sound"] == "alarm"


async def test_bark_repeat_urgent_only():
    captured = []
    n = BarkNotifier("KEY", repeat=2, repeat_interval=0, client=_mock_client(captured, {"code": 200}))
    await n.send("T", "B")
    assert len(captured) == 2
    await n.send("T", "B", urgent=False)
    assert len(captured) == 3


async def test_bark_non_urgent_is_passive():
    n = BarkNotifier("KEY")
    p = n.payload("T", "B", urgent=False)
    assert p["level"] == "passive" and "sound" not in p


async def test_telegram_bot_payload():
    captured = []
    n = TelegramBotNotifier("TOKEN", 42, client=_mock_client(captured, {"ok": True}))
    await n.send("Title", "Body")
    url, body = captured[0]
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert body == {"chat_id": 42, "text": "Title\nBody", "disable_notification": False}


class FakeNotifier:
    name = "fake"

    def __init__(self, fail_times: int = 0):
        self.calls = []
        self.fail_times = fail_times

    async def send(self, title, body, *, urgent=True):
        if self.fail_times:
            self.fail_times -= 1
            raise RuntimeError("boom")
        self.calls.append((title, body, urgent))


async def test_multi_retries_then_succeeds():
    fake = FakeNotifier(fail_times=2)
    failed = await MultiNotifier([fake], retries=3, backoff=0).send("T", "B")
    assert failed == [] and len(fake.calls) == 1


async def test_multi_reports_failure():
    fake = FakeNotifier(fail_times=5)
    assert await MultiNotifier([fake], retries=2, backoff=0).send("T", "B") == ["fake"]


def _handler(fake, **kw):
    return PowerHandler(MultiNotifier([fake], backoff=0), max_age_min=kw.get("max_age", 30),
                        notify_on_off=kw.get("on_off", False))


NOW = lambda: datetime.now(timezone.utc)  # noqa: E731


async def test_handler_notifies_on_power_on():
    fake = FakeNotifier()
    assert await _handler(fake).handle(1, ON_MSG, NOW())
    title, body, urgent = fake.calls[0]
    assert title == "💡 Світло з'явилося о 18:19" and urgent is True


async def test_handler_skips_off_by_default():
    fake = FakeNotifier()
    assert not await _handler(fake).handle(1, OFF_MSG, NOW())
    assert fake.calls == []


async def test_handler_off_quiet_when_enabled():
    fake = FakeNotifier()
    assert await _handler(fake, on_off=True).handle(1, OFF_MSG, NOW())
    assert fake.calls[0][2] is False


async def test_handler_dedup_and_stale():
    fake = FakeNotifier()
    h = _handler(fake)
    assert await h.handle(1, ON_MSG, NOW())
    assert not await h.handle(1, ON_MSG, NOW())  # дубль
    assert not await h.handle(2, ON_MSG, NOW() - timedelta(hours=2))  # застаре
    assert not await h.handle(3, "Просто текст", NOW())
    assert len(fake.calls) == 1
