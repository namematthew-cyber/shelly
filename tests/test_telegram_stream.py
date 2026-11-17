import asyncio
from types import SimpleNamespace

from aiogram.enums import ParseMode

import shelly.telegram_bot as tg


class FakeMessage:
    def __init__(self, user_id=1):
        self.chat = SimpleNamespace(id=1)
        self.from_user = SimpleNamespace(id=user_id)

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
        self.photos = []

    async def send_photo(self, **kwargs):
        self.photos.append(kwargs)
        return SimpleNamespace(message_id=98, chat=kwargs["chat_id"])

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


def test_thinking_is_animated_draft_without_duplicate_message(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    view = tg.StreamView(FakeMessage())
    asyncio.run(view.start())

    assert len(fake.drafts) == 1
    assert fake.drafts[0]["rich_message"].html == tg.THINK_HTML
    assert fake.messages == []
    assert view.use_rich is True


def test_fallback_without_drafts_uses_single_status_message(monkeypatch):
    fake = FakeBot()

    async def no_draft(**kwargs):
        raise RuntimeError("drafts disabled")

    fake.send_rich_message_draft = no_draft
    monkeypatch.setattr(tg, "bot", fake)

    view = tg.StreamView(FakeMessage())
    asyncio.run(view.start())

    assert view.use_rich is False
    assert len(fake.messages) == 1
    assert fake.messages[0]["text"] == tg.status_html()


def test_all_events_use_the_same_animated_draft(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    view = tg.StreamView(FakeMessage())
    asyncio.run(view.start())
    assert fake.drafts[-1]["rich_message"].html == tg.THINK_HTML

    asyncio.run(view._push_draft(tg.exec_html("echo ok")))
    assert "Выполняю: echo ok" in fake.drafts[-1]["rich_message"].html
    assert fake.messages == []

    asyncio.run(view._push_draft(tg.retry_html("gemini-3.1-flash-lite")))
    assert "Модель gemini-3.1-flash-lite перегружена" in fake.drafts[-1]["rich_message"].html
    assert all(d["draft_id"] == view.draft_id for d in fake.drafts)


def test_callbacks_push_status_synchronously(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    pushed = []
    view = tg.StreamView(FakeMessage())
    view._push_sync = pushed.append

    view.set_executing("run_command", {"command": "ls -la"})
    view.set_retry("gemini-3.1-flash-lite")

    assert pushed == [
        tg.exec_html("ls -la"),
        tg.retry_html("gemini-3.1-flash-lite"),
    ]


def test_command_status_lingers_before_final_answer(monkeypatch):
    import threading
    import time

    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)
    monkeypatch.setattr(tg, "MIN_COMMAND_SEC", 0.2)

    loop = asyncio.new_event_loop()
    thread = threading.Thread(target=loop.run_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(tg, "main_loop", loop)

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=5)

    try:
        view = tg.StreamView(FakeMessage())
        run(view.start())
        view.set_executing("run_command", {"command": "uptime"})
        view.set_done()

        # Сразу после команды черновик показывает именно команду.
        assert "Выполняю: uptime" in fake.drafts[-1]["rich_message"].html

        started = time.monotonic()
        run(view.hold_command())
        assert time.monotonic() - started >= 0.15
        assert "Выполняю: uptime" in fake.drafts[-1]["rich_message"].html
        run(view.close())
    finally:
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=5)
        loop.close()


def test_ask_rich_sends_only_final_answer(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)
    monkeypatch.setattr(tg, "MIN_COMMAND_SEC", 0)

    async def fake_stream(prompt, active_agent):
        return "финальный ответ"

    async def fake_send_rich(chat_id, text):
        fake.rich.append((chat_id, text))

    monkeypatch.setattr(tg, "stream_agent", fake_stream)
    monkeypatch.setattr(tg, "send_rich", fake_send_rich)

    message = FakeMessage()
    view = tg.StreamView(message)
    asyncio.run(view.start())
    asyncio.run(tg.ask_rich(message, "тест", view, object()))

    assert fake.drafts[0]["rich_message"].html == tg.THINK_HTML
    assert fake.messages == []
    assert fake.rich == [(1, "финальный ответ")]


def test_create_button_points_to_bot_management_link(monkeypatch, tmp_path):
    import re

    from shelly import texts

    monkeypatch.setattr(tg, "_bot_username", "shelly_ai")
    monkeypatch.setattr(tg, "_manage_bots", True)
    monkeypatch.setattr(tg, "BOT_NAMES_PATH", tmp_path / "names.json")
    monkeypatch.setattr(tg, "_bot_names", {"users": {}, "used": []})

    url = tg.create_bot_url(42)
    name = url.split("/")[-1].split("?")[0]
    assert url.startswith("https://t.me/newbot/shelly_ai/")
    assert url.endswith("?name=Shelly")
    assert re.fullmatch(r"shelly_ai_\d{16}_bot", name)
    assert len(name) <= 32

    keyboard = tg._inline_keyboard(texts.WELCOME_BUTTONS, 42)
    assert len(keyboard.inline_keyboard) == 1
    assert len(keyboard.inline_keyboard[0]) == 1
    button = keyboard.inline_keyboard[0][0]
    assert button.url == url
    assert button.icon_custom_emoji_id == "5258108352008823107"

    # Имя одного и того же пользователя стабильно, разные пользователи не коллидируют.
    assert tg.create_bot_url(42) == url
    assert tg.create_bot_url(43) != url

    # Без включённого режима — запасной вариант через BotFather.
    monkeypatch.setattr(tg, "_manage_bots", False)
    assert tg.create_bot_url(42) == "https://t.me/BotFather"


def test_managed_bot_returns_token_and_next_step(monkeypatch, tmp_path):
    class ManagedBot(FakeBot):
        def __init__(self):
            super().__init__()
            self.calls = []

        async def __call__(self, method):
            self.calls.append(method)
            return "123456:AA_token"

    fake = ManagedBot()
    monkeypatch.setattr(tg, "bot", fake)
    monkeypatch.setattr(tg, "_managed", {})
    image = tmp_path / "bot-created.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(tg, "BOT_CREATED_IMAGE", image)

    info = SimpleNamespace(
        user=SimpleNamespace(id=99),
        bot_user=SimpleNamespace(id=12345, username="shelly_user_bot"),
    )
    asyncio.run(tg.handle_managed_bot(info))

    assert [c.user_id for c in fake.calls] == [12345]
    assert tg._managed[99] == {
        "username": "shelly_user_bot", "token": "123456:AA_token",
    }
    assert len(fake.photos) == 1
    sent = fake.photos[0]
    assert sent["chat_id"] == 99
    assert sent["parse_mode"] == ParseMode.HTML
    assert "@shelly_user_bot" in sent["caption"]
    assert "123456:AA_token" in sent["caption"]
    assert "Дальше по шагам" in sent["caption"]
    assert "shelly-doctor" in sent["caption"]
    assert sent["reply_markup"].inline_keyboard[0][0].url == "https://t.me/shelly_user_bot"
    assert fake.messages == []


def test_managed_bot_update_is_dispatched(monkeypatch):
    from aiogram.types import ManagedBotUpdated, Update, User

    seen = []

    async def fake_handle(info):
        seen.append(info)

    monkeypatch.setattr(tg, "handle_managed_bot", fake_handle)
    user = User(id=99, is_bot=False, first_name="U")
    bot_user = User(id=12345, is_bot=True, first_name="B", username="shelly_user_bot")
    update = Update(update_id=1, managed_bot=ManagedBotUpdated(user=user, bot_user=bot_user))

    asyncio.run(tg.dp.feed_update(tg.bot, update))
    assert len(seen) == 1
    assert seen[0].bot_user.username == "shelly_user_bot"


def test_public_users_get_isolated_agents_without_commands(monkeypatch):
    from collections import OrderedDict

    created = []

    class FakeAgent:
        def __init__(self, confirm=None, public=False):
            self.confirm = confirm
            self.public = public
            created.append(self)

    monkeypatch.setattr(tg, "Agent", FakeAgent)
    monkeypatch.setattr(tg, "ADMIN_ID", 42)
    monkeypatch.setattr(tg, "_agents", OrderedDict())

    owner = tg.get_agent(42)
    user = tg.get_agent(99)
    other = tg.get_agent(100)

    assert owner.public is False
    assert owner.confirm is tg.tg_confirm
    assert user.public is True
    assert user.confirm is None
    assert other.public is True
    assert tg.get_agent(99) is user  # история одного пользователя не теряется
    assert user is not other
    assert len(created) == 3

    # Подтверждать команды может только владелец сервера.
    assert tg.is_owner(42) is True
    assert tg.is_owner(99) is False


def test_status_indicators_order_and_execution():
    assert tg.THINK_HTML.startswith("<tg-thinking><tg-emoji")
    assert " Шелли думает</tg-thinking>" in tg.THINK_HTML
    assert tg.THINK_PLAIN.startswith("💬 Шелли думает")

    executing = tg.exec_html("rm -rf /tmp/old")
    assert "Выполняю: rm -rf /tmp/old" in executing
    assert "<tg-thinking><tg-emoji" in executing
    assert "Шелли думает" not in executing
    assert tg.exec_plain("echo ok") == "💬 Выполняю: echo ok"

    retry = tg.retry_html("gemini-3.1-flash-lite")
    assert retry.startswith("<tg-thinking><tg-emoji")
    assert "Модель gemini-3.1-flash-lite перегружена" in retry


def test_dynamic_messages_have_no_signature():
    rendered = tg.rich_html("привет\nмир")
    assert "<p>привет<br/>мир</p>" in rendered
    assert "footer" not in rendered.lower()
    assert "Шелли" not in rendered


def test_static_pages_cover_full_menu():
    for page in ("menu", "about", "install", "connect", "keys", "help", "examples", "security", "clear"):
        assert page in tg.STATIC_PAGES


def test_static_pages_send_plain_html_with_keyboard(monkeypatch):
    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)

    asyncio.run(tg.send_page(1, "install"))

    sent = fake.messages[-1]
    assert sent["parse_mode"] == tg.ParseMode.HTML
    assert "<pre><code>" in sent["text"] and "tg-button" not in sent["text"]
    assert sent["reply_markup"].inline_keyboard
    assert fake.rich == []


def test_welcome_page_sends_image_with_caption_and_one_button(monkeypatch, tmp_path):
    from shelly import texts

    fake = FakeBot()
    monkeypatch.setattr(tg, "bot", fake)
    monkeypatch.setattr(tg, "_bot_username", "shelly_ai")
    monkeypatch.setattr(tg, "_manage_bots", True)
    image = tmp_path / "welcome.png"
    image.write_bytes(b"png")
    monkeypatch.setattr(tg, "WELCOME_IMAGE", image)

    asyncio.run(tg.send_page(1, "menu", 42))

    assert len(fake.photos) == 1
    sent = fake.photos[0]
    assert sent["chat_id"] == 1
    assert sent["caption"] == texts.WELCOME_HTML
    assert sent["parse_mode"] == ParseMode.HTML
    assert "disable_web_page_preview" not in sent
    keyboard = sent["reply_markup"].inline_keyboard
    assert len(keyboard) == 1
    assert len(keyboard[0]) == 1
    assert "newbot" in keyboard[0][0].url
    assert fake.messages == []


def test_start_sends_only_welcome(monkeypatch):
    calls = []

    async def fake_send(chat_id, page, user_id=None):
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
