import pytest

from power_notifier.parser import PowerEvent, PowerStatus, format_notification, parse_message

ON_MSG = """🟢 18:19 Світло з'явилося
🕓 Його не було 7год 5хв
🗓 Наступне планове: 21:30 - 00:00"""

OFF_MSG = """🔴 11:13 Світло зникло
🕓 Воно було 5год 51хв
🗓 Очікуємо за розкладом о 17:30"""


def test_parse_on():
    assert parse_message(ON_MSG) == PowerEvent(
        status=PowerStatus.ON, time="18:19", duration="7год 5хв", schedule="21:30 - 00:00"
    )


def test_parse_off():
    assert parse_message(OFF_MSG) == PowerEvent(
        status=PowerStatus.OFF, time="11:13", duration="5год 51хв", schedule="17:30"
    )


@pytest.mark.parametrize("apos", ["'", "’", "ʼ", "`", ""])
def test_on_with_any_apostrophe(apos):
    ev = parse_message(f"🟢 07:05 Світло з{apos}явилося")
    assert ev is not None and ev.status is PowerStatus.ON and ev.time == "07:05"


def test_header_line_is_ignored():
    ev = parse_message("СвітлоБот ⚡ Волошкова 2/1\n" + ON_MSG)
    assert ev is not None and ev.status is PowerStatus.ON and ev.time == "18:19"


def test_minimal_message_without_details():
    ev = parse_message("🟢 Світло з'явилося")
    assert ev == PowerEvent(status=PowerStatus.ON)


@pytest.mark.parametrize(
    "text",
    [None, "", "   ", "Графік на завтра: 09:00 - 12:00", "Світло буде о 18:00", "Дякуємо за світло!"],
)
def test_unrelated_messages(text):
    assert parse_message(text) is None


def test_format_on():
    title, body = format_notification(parse_message(ON_MSG))
    assert title == "💡 Світло з'явилося о 18:19"
    assert body == "Не було 7год 5хв\nНаступне планове: 21:30 - 00:00"


def test_format_minimal():
    title, body = format_notification(PowerEvent(status=PowerStatus.ON))
    assert title == "💡 Світло з'явилося"
    assert body == title
