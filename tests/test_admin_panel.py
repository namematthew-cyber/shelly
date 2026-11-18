import asyncio
from types import SimpleNamespace

import pytest

from shelly import admin_panel as ap
from shelly import telemetry as tel


class FakeBot:
    def __init__(self):
        self.messages = []

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=1, chat=SimpleNamespace(id=kwargs["chat_id"]))


def test_telemetry_records_safe_events(tmp_path, monkeypatch):
    monkeypatch.delenv("SHELLY_TELEMETRY_DISABLED", raising=False)
    monkeypatch.setattr(tel, "ADMIN_STATS_FILE", str(tmp_path / "stats.json"))
    monkeypatch.setattr(tel, "ADMIN_EVENTS_FILE", str(tmp_path / "events.jsonl"))
    monkeypatch.setattr(tel, "ADMIN_OFFSET_FILE", str(tmp_path / "offset"))
    monkeypatch.setattr(tel, "ADMIN_NOTIFY_EVENTS", "start,bot_created,first_task,error,service")

    assert tel.record("start", user_id=42, once=True) is True
    assert tel.record("start", user_id=42, once=True) is False
    assert tel.record("bot_created", user_id=42, detail="shelly_ai_test_bot") is True

    stats = tel.read_stats()
    assert len(stats["users"]) == 1
    assert stats["events"]["start"] == 1
    assert stats["bots"][0]["username"] == "shelly_ai_test_bot"

    events = tel.read_events()
    assert [e["event"] for e in events] == ["bot_created", "start"]
    assert all("text" not in e for e in events)
    assert tel.size_of_events() > 0
    assert tel.notify_events() == ["start", "bot_created", "first_task", "error", "service"]


def test_admin_panel_is_owner_only(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(ap, "bot", fake)
    monkeypatch.setattr(ap, "ADMIN_ID", 42)

    owner = SimpleNamespace(chat=SimpleNamespace(id=7), from_user=SimpleNamespace(id=42))
    asyncio.run(ap.cmd_stats(owner))
    assert "Панель администратора" in fake.messages[0]["text"]

    stranger = SimpleNamespace(chat=SimpleNamespace(id=8), from_user=SimpleNamespace(id=43))
    asyncio.run(ap.cmd_stats(stranger))
    assert "только владельцу" in fake.messages[1]["text"]


def test_admin_panel_event_text_has_no_private_content():
    text = ap.format_event({
        "ts": "2026-01-01T00:00:00+00:00",
        "event": "first_task",
        "user_id": 42,
        "detail": None,
    })
    assert "ID 42" in text
    assert "проверь сервер" not in text


def test_admin_panel_actions_are_allowlisted():
    with pytest.raises(ValueError):
        ap.run_action("rm -rf /")
