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


def _create(label="Создать бота"):
    # Ссылку подставляет Telegram-адаптер: она зависит от username головного бота.
    return ("create", None, label)


WELCOME_HTML = """Приветствуем!

Shelly — ИИ-агент для вашего VPS. Управляйте своим сервером из Telegram — из дома, в дороге, с телефона: бот принимает задачу и выполняет задачу на сервере. А если вы уже подключены к серверу по SSH, воспользуйтесь помощью Shelly в терминале, не открывая Telegram.

Вместо десятков команд в голове вы пишете задачу своими словами. Она выбирает команды, запускает их и возвращает готовый результат.

Чтобы подключить Shelly к своему серверу, создайте бота:"""
WELCOME_BUTTONS = ((_create(),),)

ABOUT_HTML = """<b>О Шелли</b>

<b>Шелли</b> — AI-агент для вашего VPS. Работает в Telegram и по SSH: получает задачу, выполняет команды и возвращает готовый результат.

В этом боте она отвечает на вопросы. Чтобы она работала с вашим сервером, создайте своего бота и поставьте Шелли на VPS.

Опасные действия требуют подтверждения. Ключи и токены маскируются."""
ABOUT_BUTTONS = ((_nav("menu", "Начать"),),)

INSTALL_HTML = f"""<b>Установка</b>

Понадобятся VPS с доступом по SSH, Python 3.10+ и ключ Gemini. Команды можно копировать кнопками.

<b>1. Скачайте</b>
<pre><code>git clone {_REPO_TEXT} shelly
cd shelly</code></pre>

<b>2. Установите</b>
<pre><code>sudo ./install.sh --service</code></pre>
Установщик создаст виртуальное окружение, спросит токены и поднимет systemd-сервис.

<b>3. Проверьте</b>
<pre><code>.venv/bin/shelly-doctor</code></pre>
Готово. Установщик спросит токен бота (его выдал этот бот) и ключ Gemini. Потом напишите своему боту «проверь сервер». Настройки — в <code>.env</code> с правами <code>600</code>."""
INSTALL_BUTTONS = (
    (_copy(f"git clone {_REPO_RAW} shelly && cd shelly", "1. Скачать"),),
    (_copy("sudo ./install.sh --service", "2. Установить"),),
)

CONNECT_HTML = """<b>Свой бот</b>

Этот бот отвечает на вопросы. Чтобы Шелли выполняла команды на вашем сервере, создайте бота кнопкой ниже.

После создания этот бот пришлёт токен и команды установки. Дальше работайте уже в своём боте.

Токен не публикуйте."""
CONNECT_BUTTONS = ((_create(),),)

GEMINI_KEY_HTML = f"""<b>Ключ Gemini</b>

Без ключа Шелли не сможет отвечать. Создайте его в <a href="{_KEYS_URL}">Google AI Studio</a> — ссылка есть и кнопкой ниже.

<b>Как получить</b>:
1. Войдите в Google-аккаунт.
2. Нажмите <b>Create API key</b>.
3. Скопируйте ключ (начинается с <code>AIzaSy</code> или <code>AQ.</code>).

<b>Добавьте в .env</b>:
<pre><code>GEMINI_API_KEYS=твой_ключ</code></pre>
Можно несколько ключей через запятую — Шелли переключится, если один перегружен.

Ключ не публикуйте. Если утёк — удалите его в AI Studio и создайте новый. Бесплатной квоты хватает для старта."""
GEMINI_KEY_BUTTONS = ((_url(_KEYS_URL, "Открыть AI Studio"),),)

HELP_HTML = """<b>Команды</b>

Здесь Шелли отвечает на вопросы. Чтобы она выполняла команды, создайте своего бота и установите Шелли на VPS.

<code>/start</code> — приветствие и меню
<code>/menu</code> — открыть меню
<code>/about</code> — о Шелли
<code>/install</code> — установка на VPS
<code>/connect</code> — подключить своего бота
<code>/keys</code> — ключ Gemini
<code>/examples</code> — примеры задач
<code>/security</code> — безопасность
<code>/clear</code> — очистить контекст
<code>/help</code> — эта справка

Своему боту можно написать: «проверь сервер» или «покажи логи за час»."""
HELP_BUTTONS = ((_nav("menu", "Начать"),),)

EXAMPLES_HTML = """<b>Примеры задач</b>

Нажмите кнопку — текст подставится в поле ввода, останется только отправить.

Можно написать своими словами: «проверь сервер», «какие сервисы упали», «что обновить?»."""
EXAMPLES_BUTTONS = (
    (_prompt("Проверь свободное место на дисках и покажи самое главное", "Диски"),),
    (_prompt("Покажи последние ошибки в journalctl за час", "Логи"),),
)

SECURITY_HTML = """<b>Безопасность</b>

Шелли работает на вашем сервере от имени пользователя, под которым запущена. Поэтому заложено несколько предохранителей.

• Опасные команды требуют подтверждения.
• Ключи и токены маскируются в выводе, логах и ответах.
• <code>.env</code> создаётся с правами <code>600</code>.

Проверить установку можно через <code>shelly-doctor</code>."""
SECURITY_BUTTONS = ((_nav("menu", "Начать"),),)

CLEAR_HTML = """<b>Контекст очищен 🧹</b>

Можно писать новую задачу."""
CLEAR_BUTTONS = ((_nav("menu", "Начать"),),)


def bot_created_html(username: str, token: str) -> str:
    """Сообщение после создания бота через ссылку головного бота."""
    name = html.escape("@" + str(username))
    safe_token = html.escape(str(token))
    return f"""<b>Бот {name} создан</b>

Токен: <code>{safe_token}</code> — понадобится при установке. Не публикуйте его.

<b>Дальше</b>: ключ Gemini — <a href="{_KEYS_URL}">AI Studio</a>. Потом установите Шелли:
<pre><code>git clone {_REPO_TEXT} shelly && cd shelly
sudo ./install.sh --service</code></pre>

Переходите в своего бота и пишите задачу."""


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
