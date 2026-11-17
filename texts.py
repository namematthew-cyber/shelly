"""Обычные HTML-сообщения и inline-кнопки для статических страниц бота."""

import html
import re

from .config import PROJECT_URL, USER_NAME

_NAME = html.escape(USER_NAME)
_REPO_RAW = PROJECT_URL or "<ссылка на репозиторий>"
_REPO_TEXT = html.escape(_REPO_RAW)
_KEYS_URL = "https://aistudio.google.com/app/apikey"


def _nav(page, label):
    return ("nav", page, label)


def _copy(text, label):
    return ("copy", text, label)


def _url(url, label):
    return ("url", url, label)


def _prompt(query, label):
    return ("prompt", query, label)


BACK = _nav("menu", "⬅️ Меню")
CLOSE = _nav("close", "✕ Закрыть")
BOTTOM = (BACK, CLOSE)
MAIN = (
    _nav("install", "Установить"),
    _nav("keys", "Ключ Gemini"),
    _nav("examples", "Примеры"),
)

WELCOME_HTML = f"""<b>Привет, {_NAME} 👋</b>

<b>Шелли</b> — AI-агент для вашего VPS. Поставьте её за пару команд и управляйте сервером из Telegram или терминала.

Напишите задачу — она выполнит команды и вернёт результат."""
WELCOME_BUTTONS = (
    MAIN,
    (_nav("about", "О Шелли"), _nav("security", "Безопасность"), _nav("help", "Команды"), CLOSE),
)

ABOUT_HTML = """<b>О Шелли</b>

<b>Шелли</b> — AI-агент для вашего VPS. Работает в Telegram и по SSH: получает задачу, выполняет команды и возвращает готовый результат.

Установка занимает пару команд."""
ABOUT_BUTTONS = (
    (_nav("install", "Установить"), _nav("keys", "Ключ Gemini")),
    BOTTOM,
)

INSTALL_HTML = f"""<b>Установка</b>

Три команды — и Шелли готова к работе.

<b>1. Скачайте</b>
<pre><code>git clone {_REPO_TEXT} shelly
cd shelly</code></pre>

<b>2. Установите</b>
<pre><code>sudo ./install.sh --service</code></pre>

<b>3. Проверьте</b>
<pre><code>.venv/bin/shelly-doctor</code></pre>"""
INSTALL_BUTTONS = (
    (
        _copy(f"git clone {_REPO_RAW} shelly && cd shelly", "1. Копировать"),
        _copy("sudo ./install.sh --service", "2. Копировать"),
        _copy(".venv/bin/shelly-doctor", "3. Копировать"),
    ),
    (_nav("keys", "Нужен ключ"),) + BOTTOM,
)

GEMINI_KEY_HTML = f"""<b>Ключ Gemini</b>

Создайте ключ в <a href="{_KEYS_URL}">Google AI Studio</a> и добавьте его в <code>.env</code>.

<pre><code>GEMINI_API_KEYS=твой_ключ</code></pre>

Несколько ключей можно через запятую. Ключ не публикуйте."""
GEMINI_KEY_BUTTONS = (
    (_url(_KEYS_URL, "Открыть AI Studio"), _copy("GEMINI_API_KEYS=", "Копировать")),
    (_nav("install", "К установке"),) + BOTTOM,
)

HELP_HTML = """<b>Команды</b>

<code>/start</code> — приветствие и меню
<code>/menu</code> — открыть меню
<code>/about</code> — о Шелли
<code>/install</code> — установка
<code>/keys</code> — ключ Gemini
<code>/examples</code> — примеры задач
<code>/security</code> — безопасность
<code>/clear</code> — очистить контекст
<code>/help</code> — эта справка"""
HELP_BUTTONS = (
    MAIN,
    BOTTOM,
)

EXAMPLES_HTML = """<b>Примеры задач</b>

Нажмите кнопку — текст подставится в поле ввода."""
EXAMPLES_BUTTONS = (
    (
        _prompt("Проверь свободное место на дисках и покажи самое главное", "Диски"),
        _prompt("Какие systemd-сервисы упали или перезапускались?", "Сервисы"),
    ),
    (
        _prompt("Покажи последние ошибки в journalctl за час", "Логи"),
        _prompt("Кто сейчас залогинен на сервере?", "Онлайн"),
    ),
    (
        _prompt("Проверь обновления безопасности, но ничего не устанавливай", "Обновления"),
        _prompt("Коротко расскажи, как дела на сервере", "Сводка"),
    ),
    BOTTOM,
)

SECURITY_HTML = """<b>Безопасность</b>

• Опасные команды требуют подтверждения.
• Ключи и токены маскируются в выводе и логах.
• <code>.env</code> создаётся с правами <code>600</code>."""
SECURITY_BUTTONS = (
    (_nav("install", "Установить"),) + BOTTOM,
)

CLEAR_HTML = """<b>Контекст очищен 🧹</b>

Можно писать новую задачу."""
CLEAR_BUTTONS = (BOTTOM,)


def _plain(markup: str) -> str:
    """Текст без разметки — запасной вариант, если HTML не прошёл."""
    text = re.sub(r"<[^>]+>", "", markup)
    return html.unescape(text).strip()


WELCOME_PLAIN = _plain(WELCOME_HTML)
ABOUT_PLAIN = _plain(ABOUT_HTML)
INSTALL_PLAIN = _plain(INSTALL_HTML)
GEMINI_KEY_PLAIN = _plain(GEMINI_KEY_HTML)
HELP_PLAIN = _plain(HELP_HTML)
EXAMPLES_PLAIN = _plain(EXAMPLES_HTML)
SECURITY_PLAIN = _plain(SECURITY_HTML)
CLEAR_PLAIN = _plain(CLEAR_HTML)

# Обратная совместимость для импортов по старым именам.
WELCOME = WELCOME_HTML
ABOUT = ABOUT_HTML
INSTALL = INSTALL_HTML
GEMINI_KEY = GEMINI_KEY_HTML
HELP = HELP_HTML
