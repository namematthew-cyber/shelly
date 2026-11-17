from shelly import tools
from shelly.config import setting
from shelly.texts import GEMINI_KEY, HELP, INSTALL


def test_only_one_tool():
    assert [t.name for t in tools.TOOLS] == ["run_command"]


def test_confirm_all_requires_approval(monkeypatch):
    monkeypatch.setattr(
        tools, "setting_confirm_all",
        lambda: setting("SHELLY_CONFIRM_ALL", "0") == "1",
    )
    monkeypatch.setenv("SHELLY_CONFIRM_ALL", "1")
    result = tools.run_command("echo should-not-run", confirm=lambda text: False)
    assert result["exit_code"] == 126
    assert "Отменено" in result["stderr"]


def test_run_command_masks_output(monkeypatch):
    monkeypatch.setattr(tools, "setting_confirm_all", lambda: False)
    result = tools.run_command("echo TOKEN=123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    assert "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi" not in result["stdout"]
    assert "TOKEN=***" in result["stdout"]


def test_texts_have_commands_and_install_steps():
    for command in ("/about", "/install", "/keys", "/clear", "/help"):
        assert command in HELP
    assert "git clone" in INSTALL
    assert "aistudio.google.com" in GEMINI_KEY


def test_texts_are_plain_html_with_inline_buttons():
    from shelly import texts

    pages = {
        "menu": texts.WELCOME_HTML,
        "about": texts.ABOUT_HTML,
        "install": texts.INSTALL_HTML,
        "connect": texts.CONNECT_HTML,
        "keys": texts.GEMINI_KEY_HTML,
        "help": texts.HELP_HTML,
        "examples": texts.EXAMPLES_HTML,
        "security": texts.SECURITY_HTML,
        "clear": texts.CLEAR_HTML,
    }
    buttons = {
        "menu": texts.WELCOME_BUTTONS,
        "about": texts.ABOUT_BUTTONS,
        "install": texts.INSTALL_BUTTONS,
        "connect": texts.CONNECT_BUTTONS,
        "keys": texts.GEMINI_KEY_BUTTONS,
        "help": texts.HELP_BUTTONS,
        "examples": texts.EXAMPLES_BUTTONS,
        "security": texts.SECURITY_BUTTONS,
        "clear": texts.CLEAR_BUTTONS,
    }

    for page in pages.values():
        assert "<h1>" not in page
        assert "tg-button" not in page
        assert "<b>" in page
        assert page.count("\n\n") <= 5

    assert "<pre><code>" in pages["install"]
    assert "aistudio.google.com" in pages["keys"]

    for name in ("menu", "connect"):
        assert any(spec[0] == "create" for row in buttons[name] for spec in row)
    for name in ("about", "help", "security", "clear"):
        assert any(
            spec[0] == "nav" and spec[1] == "menu"
            for row in buttons[name] for spec in row
        )

    assert any(spec[0] == "copy" for row in buttons["install"] for spec in row)
    assert any(spec[0] == "url" for row in buttons["keys"] for spec in row)
    assert any(spec[0] == "prompt" for row in buttons["examples"] for spec in row)
    assert sum(len(row) for row in buttons["menu"]) == 1

    for page in pages.values():
        assert "ID" not in page
        assert "характер" not in page.lower()
        assert "архитектур" not in page.lower()

    assert "<" not in texts.WELCOME_PLAIN
    assert "Шелли" in texts.WELCOME_PLAIN


def test_static_pages_go_one_step_at_a_time():
    from shelly import texts

    pages = {
        "menu": texts.WELCOME_BUTTONS,
        "about": texts.ABOUT_BUTTONS,
        "install": texts.INSTALL_BUTTONS,
        "connect": texts.CONNECT_BUTTONS,
        "keys": texts.GEMINI_KEY_BUTTONS,
        "help": texts.HELP_BUTTONS,
        "examples": texts.EXAMPLES_BUTTONS,
        "security": texts.SECURITY_BUTTONS,
        "clear": texts.CLEAR_BUTTONS,
    }
    for name, rows in pages.items():
        assert all(len(row) == 1 for row in rows), name
        assert sum(len(row) for row in rows) <= 2, name

    # В приветствии нет кнопки «Закрыть» — только действия по установке.
    assert not any(
        spec[:2] == ("nav", "close")
        for row in texts.WELCOME_BUTTONS for spec in row
    )
    assert "из Telegram можно выполнять любые команды" in texts.WELCOME_HTML
    assert "задеплоить код" in texts.WELCOME_HTML
    assert "прямо в терминале" in texts.WELCOME_HTML

