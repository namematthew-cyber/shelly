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


def test_texts_are_rich_and_readable():
    from shelly.texts import (
        ABOUT_HTML, HELP_HTML, INSTALL_HTML, WELCOME_HTML, WELCOME_PLAIN,
    )

    assert "<h1>" in WELCOME_HTML
    assert WELCOME_HTML.count("<p><br/></p>") >= 5
    assert HELP_HTML.count("<p><br/></p>") >= 4
    assert "<tg-button-row>" in WELCOME_HTML
    assert "nav:about" in WELCOME_HTML
    assert "<ol>" in INSTALL_HTML and "<code>" in INSTALL_HTML
    assert "<ul>" in ABOUT_HTML and "<footer>" in ABOUT_HTML
    assert "<ul>" in HELP_HTML
    assert "<h1>" not in WELCOME_PLAIN
    assert "Шелли" in WELCOME_PLAIN
