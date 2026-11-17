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
        self.messages = []

    async def send_rich_message_draft(self, **kwargs):
        self.drafts.append(kwargs)

    async def send_rich_message(self, **kwargs):
        self.rich.append(kwargs)

    async def send_message(self, **kwargs):
        self.messages.append(kwargs)
        return SimpleNamespace(message_id=99, chat=kwargs["chat_id"])

    async def edit_message_text(self, **kwargs):
        self.edits.append(kwargs)

    async def delete_message(self, **kwargs):
        self.deleted.append(kwargs)


def test_status_sequence_uses_one_message(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    view = tg.StreamView(FakeMessage())
    asyncio.run(view.start())
    assert len(fake.messages) == 1
    assert fake.messages[-1]["text"] == tg.status_html()

    asyncio.run(view._push_status(tg.status_html(command="echo ok")))
    assert len(fake.messages) == 1
    assert fake.edits[-1]["text"] == tg.status_html(command="echo ok")
    assert "tg-emoji" in fake.edits[-1]["text"]

    asyncio.run(view._push_status(tg.status_html(retry_model="gemini-3.1-flash-lite")))
    assert "Проверяю модель gemini-3.1-flash-lite" in fake.edits[-1]["text"]

    asyncio.run(view.close())
    assert fake.deleted[-1]["message_id"] == 99


def test_ask_rich_sends_only_final_answer(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    async def fake_stream(prompt):
        return "финальный ответ"

    async def fake_send_rich(chat_id, text):
        fake.rich.append((chat_id, text))

    monkeypatch.setattr(tg, "stream_agent", fake_stream)
    monkeypatch.setattr(tg, "send_rich", fake_send_rich)

    message = FakeMessage()
    view = tg.StreamView(message)
    asyncio.run(view.start())
    asyncio.run(tg.ask_rich(message, "тест", view))

    assert len(fake.messages) == 1
    assert fake.deleted[0]["message_id"] == 99
    assert fake.rich == [(1, "финальный ответ")]


def test_status_indicators_order_and_execution():
    assert tg.THINK_HTML.startswith("<tg-thinking><tg-emoji")
    assert " Шелли думает</tg-thinking>" in tg.THINK_HTML
    assert tg.THINK_PLAIN.startswith("💬 Шелли думает")

    executing = tg.exec_html("rm -rf /tmp/old")
    assert "Выполняю: rm -rf /tmp/old" in executing
    assert "<tg-thinking><tg-emoji" in executing
    assert "Шелли думает" not in executing
    assert tg.exec_plain("echo ok") == "💬 Выполняю: echo ok"


def test_dynamic_messages_have_no_signature():
    rendered = tg.rich_html("привет\nмир")
    assert "<p>привет<br/>мир</p>" in rendered
    assert "footer" not in rendered.lower()
    assert "Шелли" not in rendered


def test_static_pages_cover_full_menu():
    for page in ("menu", "about", "install", "keys", "help", "examples", "security", "clear"):
        assert page in tg.STATIC_PAGES


def test_static_pages_send_plain_html_with_keyboard(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    asyncio.run(tg.send_page(1, "install"))

    sent = fake.messages[-1]
    assert sent["parse_mode"] == tg.ParseMode.HTML
    assert "<b>" in sent["text"] and "tg-button" not in sent["text"]
    assert sent["reply_markup"].inline_keyboard
    assert fake.rich == []


def test_start_sends_only_welcome(monkeypatch):
    calls = []

    async def fake_send(chat_id, page):
        calls.append(page)

    async def fake_ask(message, prompt):
        calls.append("agent")

    monkeypatch.setattr(tg, "send_page", fake_send)
    monkeypatch.setattr(tg, "ask", fake_ask)

    message = SimpleNamespace(
        from_user=SimpleNamespace(id=1),
        chat=SimpleNamespace(id=1),
    )
    asyncio.run(tg.cmd_start(message))

    assert calls == ["menu"]
