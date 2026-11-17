"""Статичные rich-страницы Telegram-бота: меню, установка, ключи, примеры, справка."""

import html
import re

from .config import PROJECT_URL, USER_NAME

_NAME = html.escape(USER_NAME)
_REPO_RAW = PROJECT_URL or "<ссылка на репозиторий>"
_REPO_TEXT = html.escape(_REPO_RAW)
_REPO_LINK = (
    f'<a href="{html.escape(PROJECT_URL, quote=True)}">{_REPO_TEXT}</a>'
    if PROJECT_URL else _REPO_TEXT
)

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


BACK = _nav("menu", "⬅️ Главное меню")
CLOSE = _nav("close", "✕ Закрыть")
BOTTOM = _row(BACK, CLOSE)

WELCOME_HTML = f"""<h1>Привет, {_NAME} 👋</h1>
{AIR}
<p>Я <b>Шелли</b> — агентный AI-ассистент администратора сервера.</p>
{AIR}
<p>Получаю задачу, выполняю команду, читаю результат и думаю дальше. Инструмент ровно один — <code>run_command</code>. Спокойная, когда спокойно; с юмором всегда; в инциденте — собранная и быстрая.</p>
{AIR}
<hr/>
{AIR}
<h2>Куда пойдём?</h2>
{AIR}
<ul>
<li><b>О проекте</b> — как я устроена и где работаю.</li>
<li><b>Установка</b> — три команды до работающего бота.</li>
<li><b>Ключ Gemini</b> — где взять и как не потерять.</li>
<li><b>Примеры</b> — готовые задачи одним нажатием.</li>
</ul>
{AIR}
<p>Можешь просто написать задачу текстом. Опасные команды всегда спросят подтверждения.</p>
{AIR}
{_row(_nav('about', 'О проекте'), _nav('install', 'Установка'), _nav('keys', 'Ключ Gemini'), _nav('help', 'Справка'))}
{AIR}
{_row(_nav('examples', 'Примеры задач'), _nav('security', 'Безопасность'), CLOSE)}
{AIR}
<footer>Один инструмент. Много заботы.</footer>"""

ABOUT_HTML = f"""<h1>Что такое Шелли</h1>
{AIR}
<p><b>Шелли</b> — агентный AI-ассистент администратора сервера. Работает в терминале по SSH и в Telegram, поверх одного и того же ядра.</p>
{AIR}
<h2>Как устроена</h2>
{AIR}
<ul>
<li>Модель сама решает, когда вызвать инструмент.</li>
<li>Инструмент один — <code>run_command</code>, без лишнего реестра.</li>
<li>Результат команды возвращается модели, и цикл продолжается до ответа.</li>
<li>Ответ стримится прямо в чат, а во время команды видно «Выполняю: …».</li>
</ul>
{AIR}
<h2>Характер</h2>
{AIR}
<p>Спокойная в спокойном диалоге, с юмором всегда, при тревоге переключается в режим инцидента.</p>
{AIR}
<hr/>
{AIR}
<p>Исходники: {_REPO_LINK}</p>
{AIR}
{BOTTOM}"""

INSTALL_HTML = f"""<h1>Установка на свой сервер</h1>
{AIR}
<p>Нужны: Python 3.10+, SSH-доступ и ключ Gemini. Кнопки ниже копируют команды — можно не перепечатывать.</p>
{AIR}
<h2>1. Скачай исходники</h2>
{AIR}
<pre><code>git clone {_REPO_TEXT} shelly
cd shelly</code></pre>
{AIR}
<p>{_copy(f'git clone {_REPO_RAW} shelly && cd shelly')}</p>
{AIR}
<h2>2. Запусти установку</h2>
{AIR}
<pre><code>sudo ./install.sh --service</code></pre>
{AIR}
<p>{_copy('sudo ./install.sh --service')}</p>
{AIR}
<p>Создаст виртуальное окружение, поставит пакет, спросит токены и поднимет systemd-сервис.</p>
{AIR}
<h2>3. Проверь результат</h2>
{AIR}
<pre><code>.venv/bin/shelly-doctor</code></pre>
{AIR}
<p>{_copy('.venv/bin/shelly-doctor')}</p>
{AIR}
<p>Без сервиса: <code>.venv/bin/shelly</code> — терминал, <code>.venv/bin/shelly-tg</code> — Telegram.</p>
{AIR}
<blockquote>Настройки лежат в <code>.env</code> рядом с пакетом, права <code>600</code>. Там нужны <code>GEMINI_API_KEYS</code>, <code>SHELLY_TG_TOKEN</code>, <code>SHELLY_ADMIN_ID</code>.</blockquote>
{AIR}
{_row(_nav('keys', 'Получить ключ'), _nav('security', 'Безопасность'))}
{AIR}
{BOTTOM}"""

GEMINI_KEY_HTML = f"""<h1>Ключ Gemini за 2 минуты</h1>
{AIR}
<ol>
<li>Открой <a href="https://aistudio.google.com/app/apikey">Google AI Studio → API keys</a>.</li>
<li>Войди в Google-аккаунт.</li>
<li>Нажми <b>Create API key</b> и выбери проект или создай новый.</li>
<li>Скопируй ключ (начинается с <code>AIzaSy</code> или <code>AQ.</code>) и добавь в <code>.env</code>.</li>
</ol>
{AIR}
<pre><code>GEMINI_API_KEYS=твой_ключ</code></pre>
{AIR}
<p>{_url('https://aistudio.google.com/app/apikey', 'Открыть AI Studio')} {_copy('GEMINI_API_KEYS=')}</p>
{AIR}
<blockquote>Несколько ключей через запятую — Шелли переключится, если один перегружен или исчерпал квоту.</blockquote>
{AIR}
<p>Не публикуй ключ. Если утёк — удали его в Google AI Studio и создай новый. Бесплатной квоты хватает для старта; для постоянной работы включи billing.</p>
{AIR}
{_row(_nav('install', 'К установке'), _nav('menu', 'Главное меню'), CLOSE)}"""

HELP_HTML = f"""<h1>Справка</h1>
{AIR}
<p>Вот что я умею по командам.</p>
{AIR}
<ul>
<li><code>/start</code> — приветствие и главное меню</li>
<li><code>/menu</code> — открыть меню заново</li>
<li><code>/about</code> — что такое Шелли</li>
<li><code>/install</code> — как поставить на свой сервер</li>
<li><code>/keys</code> — как получить ключ Gemini</li>
<li><code>/examples</code> — готовые задачи</li>
<li><code>/security</code> — как защищены секреты</li>
<li><code>/clear</code> — забыть историю разговора</li>
<li><code>/help</code> — эта справка</li>
</ul>
{AIR}
<hr/>
{AIR}
<p>Просто напиши задачу текстом — выполню её на сервере. Опасные команды спросят подтверждения кнопками «Да» и «Нет».</p>
{AIR}
{_row(_nav('about', 'О проекте'), _nav('install', 'Установка'), _nav('keys', 'Ключ'), _nav('examples', 'Примеры'))}
{AIR}
{BOTTOM}"""

EXAMPLES_HTML = f"""<h1>Примеры задач</h1>
{AIR}
<p>Нажми кнопку — текст подставится в поле ввода. Остаётся только отправить.</p>
{AIR}
<ul>
<li>Проверить диск, память и нагрузку.</li>
<li>Найти падающие systemd-сервисы.</li>
<li>Показать последние ошибки в логах.</li>
<li>Узнать, кто сейчас залогинен на сервере.</li>
<li>Проверить, есть ли обновления безопасности.</li>
</ul>
{AIR}
{_row(_prompt('Проверь свободное место на дисках и покажи самое главное', 'Диски и память'), _prompt('Какие systemd-сервисы упали или перезапускались?', 'Сервисы'))}
{AIR}
{_row(_prompt('Покажи последние ошибки в journalctl за час', 'Ошибки в логах'), _prompt('Кто сейчас залогинен на сервере?', 'Кто онлайн'))}
{AIR}
{_row(_prompt('Проверь, есть ли обновления безопасности, но ничего не устанавливай', 'Обновления'), _prompt('Коротко расскажи, как дела на сервере', 'Сводка'))}
{AIR}
{BOTTOM}"""

SECURITY_HTML = f"""<h1>Безопасность</h1>
{AIR}
<p>Шелли работает на твоём сервере и видит то, что разрешил ей пользователь. Поэтому заложено несколько предохранителей.</p>
{AIR}
<ul>
<li>В Telegram отвечает только один разрешённый ID.</li>
<li>Опасные команды требуют подтверждения кнопками.</li>
<li>Вывод команд и аудит-лог проходят маскировку секретов.</li>
<li>Файл <code>.env</code> создаётся с правами <code>600</code>.</li>
<li>Проверить установку можно через <code>shelly-doctor</code>.</li>
</ul>
{AIR}
<blockquote>Если включить <code>SHELLY_CONFIRM_ALL=1</code>, подтверждение потребуется для любой команды.</blockquote>
{AIR}
{_row(_nav('install', 'К установке'), _nav('keys', 'Ключ'), _nav('menu', 'Главное меню'), CLOSE)}"""

CLEAR_HTML = f"""<h2>Контекст очищен 🧹</h2>
{AIR}
<p>Начнём с чистого листа — как после перезагрузки, только без тревожных звуков.</p>
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
