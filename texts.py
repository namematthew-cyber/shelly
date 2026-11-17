"""Короткие rich-страницы Telegram-бота: меньше слов, больше действия."""

import html
import re

from .config import PROJECT_URL, USER_NAME

_NAME = html.escape(USER_NAME)
_REPO_RAW = PROJECT_URL or "<ссылка на репозиторий>"
_REPO_TEXT = html.escape(_REPO_RAW)

AIR = "<p><br/></p>"


def _nav(page, label):
    return f'<tg-button type="callback_data" data="nav:{page}">{html.escape(label)}</tg-button>'


def _copy(text, label="Копировать"):
    return (
        f'<tg-button type="copy_text" text="{html.escape(text, quote=True)}">'
        f"{html.escape(label)}</tg-button>"
    )


def _url(url, label):
    return (
        f'<tg-button type="url" url="{html.escape(url, quote=True)}">'
        f"{html.escape(label)}</tg-button>"
    )


def _prompt(query, label):
    return (
        f'<tg-button type="switch_inline_query_current_chat" query="{html.escape(query, quote=True)}">'
        f"{html.escape(label)}</tg-button>"
    )


def _row(*buttons):
    return "<tg-button-row>" + "".join(buttons) + "</tg-button-row>"


BACK = _nav("menu", "⬅️ Меню")
CLOSE = _nav("close", "✕ Закрыть")
BOTTOM = _row(BACK, CLOSE)

WELCOME_HTML = f"""<h1>Привет, {_NAME} 👋</h1>
{AIR}
<p><b>Шелли</b> — AI-агент для вашего VPS. Поставьте её за пару команд и управляйте сервером из Telegram или терминала.</p>
<p>Напишите задачу — она выполнит команды и вернёт результат.</p>
{AIR}
{_row(_nav('install', 'Установить'), _nav('keys', 'Ключ Gemini'), _nav('examples', 'Примеры'))}
{AIR}
{_row(_nav('about', 'О Шелли'), _nav('security', 'Безопасность'), _nav('help', 'Команды'), CLOSE)}"""

ABOUT_HTML = f"""<h1>О Шелли</h1>
{AIR}
<p><b>Шелли</b> — AI-агент для вашего VPS. Работает в Telegram и по SSH: получает задачу, выполняет команды и возвращает готовый результат.</p>
<p>Установка занимает пару команд.</p>
{AIR}
{_row(_nav('install', 'Установить'), _nav('keys', 'Ключ Gemini'))}
{AIR}
{BOTTOM}"""

INSTALL_HTML = f"""<h1>Установка</h1>
{AIR}
<p>Три команды — и Шелли готова к работе.</p>
<h2>1. Скачайте</h2>
<pre><code>git clone {_REPO_TEXT} shelly
cd shelly</code></pre>
<p>{_copy(f'git clone {_REPO_RAW} shelly && cd shelly')}</p>
<h2>2. Установите</h2>
<pre><code>sudo ./install.sh --service</code></pre>
<p>{_copy('sudo ./install.sh --service')}</p>
<h2>3. Проверьте</h2>
<pre><code>.venv/bin/shelly-doctor</code></pre>
<p>{_copy('.venv/bin/shelly-doctor')}</p>
{AIR}
{_row(_nav('keys', 'Нужен ключ'), _nav('menu', 'Меню'), CLOSE)}"""

GEMINI_KEY_HTML = f"""<h1>Ключ Gemini</h1>
{AIR}
<p>Создайте ключ в Google AI Studio и добавьте его в <code>.env</code>.</p>
{AIR}
<p>{_url('https://aistudio.google.com/app/apikey', 'Открыть AI Studio')} {_copy('GEMINI_API_KEYS=')}</p>
<pre><code>GEMINI_API_KEYS=твой_ключ</code></pre>
<p>Несколько ключей можно через запятую. Ключ не публикуйте.</p>
{AIR}
{_row(_nav('install', 'К установке'), _nav('menu', 'Меню'), CLOSE)}"""

HELP_HTML = f"""<h1>Команды</h1>
{AIR}
<ul>
<li><code>/start</code> — приветствие и меню</li>
<li><code>/menu</code> — открыть меню</li>
<li><code>/about</code> — о Шелли</li>
<li><code>/install</code> — установка</li>
<li><code>/keys</code> — ключ Gemini</li>
<li><code>/examples</code> — примеры задач</li>
<li><code>/security</code> — безопасность</li>
<li><code>/clear</code> — очистить контекст</li>
<li><code>/help</code> — эта справка</li>
</ul>
{AIR}
{_row(_nav('install', 'Установить'), _nav('keys', 'Ключ'), _nav('examples', 'Примеры'))}
{AIR}
{BOTTOM}"""

EXAMPLES_HTML = f"""<h1>Примеры задач</h1>
{AIR}
<p>Нажмите кнопку — текст подставится в поле ввода.</p>
{AIR}
{_row(_prompt('Проверь свободное место на дисках и покажи самое главное', 'Диски'), _prompt('Какие systemd-сервисы упали или перезапускались?', 'Сервисы'))}
{_row(_prompt('Покажи последние ошибки в journalctl за час', 'Логи'), _prompt('Кто сейчас залогинен на сервере?', 'Онлайн'))}
{_row(_prompt('Проверь обновления безопасности, но ничего не устанавливай', 'Обновления'), _prompt('Коротко расскажи, как дела на сервере', 'Сводка'))}
{AIR}
{BOTTOM}"""

SECURITY_HTML = f"""<h1>Безопасность</h1>
{AIR}
<ul>
<li>Опасные команды требуют подтверждения.</li>
<li>Ключи и токены маскируются в выводе и логах.</li>
<li><code>.env</code> создаётся с правами <code>600</code>.</li>
</ul>
{AIR}
{_row(_nav('install', 'Установить'), _nav('menu', 'Меню'), CLOSE)}"""

CLEAR_HTML = f"""<h2>Контекст очищен 🧹</h2>
<p>Можно писать новую задачу.</p>
{AIR}
{BOTTOM}"""


def _plain(markup: str) -> str:
    """Plain-версия для клиентов без rich-сообщений."""
    text = re.sub(r"<tg-button\b[^>]*>.*?</tg-button>", "", markup, flags=re.S)
    text = re.sub(
        r"</?(?:p|h[1-6]|li|ol|ul|hr|footer|blockquote|tg-button-row)[^>]*>",
        "\n", text,
    )
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
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
