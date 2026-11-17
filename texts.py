"""Обычные HTML-сообщения и inline-кнопки для статических страниц бота."""

import html
import re

from .config import PROJECT_URL, USER_NAME

_NAME = html.escape(USER_NAME)
_REPO_RAW = PROJECT_URL or "https://github.com/namematthew-cyber/shelly"
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


def _create(label="Создать бота"):
    # Ссылку подставляет Telegram-адаптер: она зависит от username головного бота.
    return ("create", None, label)


WELCOME_HTML = """Приветствуем!

С помощью Shelly вы можете управлять своим VPS через Telegram: бот принимает задачу и работает на сервере. Shelly также поможет в работе непосредственно в терминале.

Вместо десятков команд в голове вы пишете задачу своими словами. Shelly выбирает команды, запускает их и возвращает готовый результат.

Чтобы подключить Shelly к своему серверу, создайте бота:"""
WELCOME_BUTTONS = ((_create(),),)

ABOUT_HTML = """Shelly работает на вашем VPS: задачи из Telegram и из терминала по SSH, выполнение команд и готовый результат.

Чтобы она работала с вашим сервером, создайте своего бота и установите Shelly на VPS.

Опасные команды требуют подтверждения, ключи и токены маскируются."""
ABOUT_BUTTONS = ((_nav("menu", "Начать"),),)

INSTALL_HTML = f"""Установка на VPS. Нужны SSH, Python 3.10+ и ключ Gemini.

1. Скачайте:
<pre><code>git clone {_REPO_TEXT} shelly
cd shelly</code></pre>

2. Установите:
<pre><code>sudo ./install.sh --service</code></pre>

3. Проверьте:
<pre><code>.venv/bin/shelly-doctor</code></pre>

Установщик спросит токен бота и ключ Gemini. Дальше пишите задачу своему боту."""
INSTALL_BUTTONS = (
    (_copy(f"git clone {_REPO_RAW} shelly && cd shelly", "1. Скачать"),),
    (_copy("sudo ./install.sh --service", "2. Установить"),),
)

CONNECT_HTML = """Свой бот нужен для работы с вашим сервером.

Создайте его кнопкой ниже — этот бот пришлёт токен и команды установки. Дальше работайте уже в своём боте.

Токен не публикуйте."""
CONNECT_BUTTONS = ((_create(),),)

GEMINI_KEY_HTML = f"""Ключ Gemini.

Без ключа Shelly не сможет отвечать. Получите его в <a href="{_KEYS_URL}">AI Studio</a> кнопкой Create API key.

Добавьте в <code>.env</code>:
<pre><code>GEMINI_API_KEYS=ваш_ключ</code></pre>

Можно несколько ключей через запятую. Ключ не публикуйте, при утечке удалите его в AI Studio."""
GEMINI_KEY_BUTTONS = ((_url(_KEYS_URL, "Открыть AI Studio"),),)

HELP_HTML = """Этот бот отвечает на вопросы и помогает с установкой. Для работы с сервером создайте своего бота.

<code>/start</code> — приветствие
<code>/menu</code> — меню
<code>/about</code> — что умеет Shelly
<code>/install</code> — установка
<code>/connect</code> — свой бот
<code>/keys</code> — ключ Gemini
<code>/examples</code> — примеры задач
<code>/security</code> — безопасность
<code>/clear</code> — очистить контекст
<code>/help</code> — справка"""
HELP_BUTTONS = ((_nav("menu", "Начать"),),)

EXAMPLES_HTML = """Примеры задач.

Нажмите кнопку — текст подставится в поле ввода. Или напишите своими словами: «проверь сервер», «покажи логи за час»."""
EXAMPLES_BUTTONS = (
    (_prompt("Проверь свободное место на дисках и покажи самое главное", "Диски"),),
    (_prompt("Покажи последние ошибки в journalctl за час", "Логи"),),
)

SECURITY_HTML = """Безопасность.

Shelly работает на вашем сервере от имени пользователя, под которым запущена.

• Опасные команды требуют подтверждения.
• Ключи и токены маскируются в ответе и логах.
• <code>.env</code> создаётся с правами <code>600</code>.

Проверка: <code>.venv/bin/shelly-doctor</code>."""
SECURITY_BUTTONS = ((_nav("menu", "Начать"),),)

CLEAR_HTML = """Контекст очищен.

Можно писать новую задачу."""
CLEAR_BUTTONS = ((_nav("menu", "Начать"),),)


def bot_created_html(username: str, token: str) -> str:
    """Сообщение после создания бота через ссылку головного бота."""
    name = html.escape("@" + str(username))
    safe_token = html.escape(str(token))
    return f"""Бот {name} создан.

Токен: <code>{safe_token}</code>. Он понадобится при установке — не публикуйте его.

Дальше по шагам.

1. Получите ключ Gemini: <a href="{_KEYS_URL}">AI Studio</a> → Create API key.

2. Зайдите на свой VPS по SSH и выполните:
<pre><code>git clone {_REPO_TEXT} shelly && cd shelly
sudo ./install.sh --service</code></pre>
Установщик спросит токен бота и ключ Gemini — вставьте их.

3. Проверьте установку:
<pre><code>.venv/bin/shelly-doctor</code></pre>

4. Переходите в своего бота и пишите задачу, например «проверь сервер»."""


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
CONNECT_PLAIN = _plain(CONNECT_HTML)
CLEAR_PLAIN = _plain(CLEAR_HTML)

# Обратная совместимость для импортов по старым именам.
WELCOME = WELCOME_HTML
ABOUT = ABOUT_HTML
INSTALL = INSTALL_HTML
GEMINI_KEY = GEMINI_KEY_HTML
HELP = HELP_HTML
