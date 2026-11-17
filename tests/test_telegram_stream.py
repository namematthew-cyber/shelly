import asyncio
from types import SimpleNamespace

import shelly.telegram_bot as tg


class FakeMessage:
    def __init__(self):
        self.chat = SimpleNamespace(id=1)

    async def answer(self, text):
        assert text == tg.THINK_PLAIN
        return SimpleNamespace(message_id=7, chat=self.chat)


class FakeBot:
    def __init__(self):
        self.drafts = []
        self.edits = []
        self.deleted = []
        self.rich = []

    async def send_rich_message_draft(self, **kwargs):
        self.drafts.append(kwargs)

    async def send_rich_message(self, **kwargs):
        self.rich.append(kwargs)

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)

    async def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


def test_long_request_uses_editable_keepalive(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)
    monkeypatch.setattr(tg, "LONG_REQUEST_AFTER", 0.1)
    monkeypatch.setattr(tg, "rich_html", lambda text: text)

    async def fake_stream(prompt, data, lock, on_delta, sender):
        await sender("часть ответа", 0.2)
        return "финальный ответ"

    async def fake_send_rich(chat_id, text):
        fake.rich.append((chat_id, text))

    monkeypatch.setattr(tg, "stream_agent", fake_stream)
    monkeypatch.setattr(tg, "send_rich", fake_send_rich)

    asyncio.run(tg.ask_rich(FakeMessage(), "тест", 123))

    assert len(fake.drafts) == 1
    assert len(fake.edits) == 1
    assert fake.deleted[0]["message_id"] == 7
    assert fake.rich == [(1, "финальный ответ")]


def test_dynamic_messages_have_no_signature():
    rendered = tg.rich_html("привет\nмир")
    assert "<p>привет<br/>мир</p>" in rendered
    assert "footer" not in rendered.lower()
    assert "Шелли" not in rendered


def test_start_sends_only_welcome(monkeypatch):
    calls = []

    async def fake_send(chat_id, markup, plain):
        calls.append("welcome")

    async def fake_ask(message, prompt):
        calls.append("agent")

    monkeypatch.setattr(tg, "send_rich_html", fake_send)
    monkeypatch.setattr(tg, "ask", fake_ask)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        chat=SimpleNamespace(id=1),
    )
    asyncio.run(tg.cmd_start(message))

    assert calls == ["welcome"]
