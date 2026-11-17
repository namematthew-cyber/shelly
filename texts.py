"""Статичные rich-тексты: приветствие, о проекте, установка, ключи, справка."""

import html
import re

from .config import PROJECT_URL, USER_NAME

_NAME = html.escape(USER_NAME)
_REPO_TEXT = html.escape(PROJECT_URL or "<ссылка на репозиторий>")
_REPO_LINK = (
    f'<a href="{html.escape(PROJECT_URL, quote=True)}">{_REPO_TEXT}</a>'
    if PROJECT_URL else _REPO_TEXT
)

WELCOME_HTML = f"""<h1>Привет, {_NAME} 👋</h1>
<p>Я <b>Шелли</b> — агентный AI-ассистент администратора сервера.</p>
<p>Не болталка: получаю задачу, выполняю команду, читаю результат и думаю дальше. Инструмент ровно один — <code>run_command</code>. Спокойная, когда спокойно; с юмором всегда; в инциденте — собранная и быстрая.</p>
<hr/>
<h2>С чего начать</h2>
<ol>
<li><b>Узнать, что я умею</b> — кнопка «О проекте» или <code>/about</code>.</li>
<li><b>Поставить себе</b> — <code>/install</code>.</li>
<li><b>Получить ключ Gemini</b> — <code>/keys</code>.</li>
</ol>
<p>Можешь просто написать задачу текстом. Опасные команды всегда спросят подтверждения.</p>
<tg-button-row>
<tg-button type="callback_data" data="nav:about">О проекте</tg-button>
<tg-button type="callback_data" data="nav:install">Установка</tg-button>
<tg-button type="callback_data" data="nav:keys">Ключ Gemini</tg-button>
<tg-button type="callback_data" data="nav:help">Справка</tg-button>
</tg-button-row>
<footer>Один инструмент. Много заботы.</footer>"""

ABOUT_HTML = f"""<h1>Что такое Шелли</h1>
<p><b>Шелли</b> — агентный AI-ассистент администратора сервера. Работает в терминале по SSH и в Telegram, поверх одного и того же ядра.</p>
<h2>Как устроена</h2>
<ul>
<li>Модель сама решает, когда вызвать инструмент.</li>
<li>Инструмент один — <code>run_command</code>, без лишнего реестра.</li>
<li>Результат команды возвращается модели, и цикл продолжается до ответа.</li>
</ul>
<h2>Характер</h2>
<p>Спокойная в спокойном диалоге, с юмором всегда, при тревоге переключается в режим инцидента.</p>
<hr/>
<p>Исходники: {_REPO_LINK}</p>
<footer>Дальше — /install и /keys</footer>"""

INSTALL_HTML = f"""<h1>Установка на свой сервер</h1>
<p>Нужны: Python 3.10+, SSH-доступ и ключ Gemini.</p>
<ol>
<li><b>Скачай исходники</b><pre><code>git clone {_REPO_TEXT} shelly
cd shelly</code></pre></li>
<li><b>Запусти установку</b><pre><code>sudo ./install.sh --service</code></pre>
<p>Создаст venv, поставит пакет, спросит токены и поднимет systemd-сервис.</p></li>
<li><b>Или без сервиса</b><pre><code>./install.sh
.venv/bin/shelly      # терминал
.venv/bin/shelly-tg   # Telegram
.venv/bin/shelly-doctor # проверка</code></pre></li>
<li><b>Настройки</b> — в <code>.env</code> рядом с пакетом, права <code>600</code>. Нужны <code>GEMINI_API_KEYS</code>, <code>SHELLY_TG_TOKEN</code>, <code>SHELLY_ADMIN_ID</code>.</li>
</ol>
<blockquote>Ссылка на репозиторий пока заглушка, если владелец не задал <code>SHELLY_PROJECT_URL</code>.</blockquote>
<footer>Подробности — README.md в репозитории</footer>"""

GEMINI_KEY_HTML = f"""<h1>Ключ Gemini за 2 минуты</h1>
<ol>
<li>Открой <a href="https://aistudio.google.com/app/apikey">Google AI Studio → API keys</a>.</li>
<li>Войди в свой Google-аккаунт.</li>
<li>Нажми <b>Create API key</b> и выбери существующий проект или создай новый.</li>
<li>Скопируй ключ (начинается с <code>AIzaSy</code> или <code>AQ.</code>) и добавь в <code>.env</code>:</li>
</ol>
<pre><code>GEMINI_API_KEYS=твой_ключ</code></pre>
<blockquote>Несколько ключей перечисляются через запятую — Шелли переключится, если один перегружен или исчерпал квоту.</blockquote>
<p>Не публикуй ключ. Если утёк — удали его в Google AI Studio и создай новый. Бесплатной квоты хватает для старта; для постоянной работы включи billing.</p>
<footer>То же самое: /keys в боте</footer>"""

HELP_HTML = """<h1>Справка</h1>
<ul>
<li><code>/start</code> — приветствие и быстрый старт</li>
<li><code>/about</code> — что такое Шелли</li>
<li><code>/install</code> — как поставить на свой сервер</li>
<li><code>/keys</code> — как получить ключ Gemini</li>
<li><code>/clear</code> — забыть историю разговора</li>
<li><code>/help</code> — эта справка</li>
</ul>
<hr/>
<p>Просто напиши задачу текстом — выполню её на сервере. Опасные команды спросят подтверждения кнопками «Да» и «Нет».</p>
<tg-button-row>
<tg-button type="callback_data" data="nav:about">О проекте</tg-button>
<tg-button type="callback_data" data="nav:install">Установка</tg-button>
<tg-button type="callback_data" data="nav:keys">Ключ</tg-button>
</tg-button-row>
<footer>Напиши задачу — и я возьмусь</footer>"""

CLEAR_HTML = """<h2>Контекст очищен 🧹</h2>
<p>Начнём с чистого листа — как после перезагрузки, только без тревожных звуков.</p>
<footer>Можно смело писать новую задачу</footer>"""


def _plain(markup: str) -> str:
    """Plain-версия для клиентов без rich-сообщений."""
    text = re.sub(
        r"</?(?:p|h[1-6]|li|ol|ul|hr|footer|blockquote|tg-button-row)[^>]*>",
        "\n", markup,
    )
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


WELCOME_PLAIN = _plain(WELCOME_HTML)
ABOUT_PLAIN = _plain(ABOUT_HTML)
INSTALL_PLAIN = _plain(INSTALL_HTML)
GEMINI_KEY_PLAIN = _plain(GEMINI_KEY_HTML)
HELP_PLAIN = _plain(HELP_HTML)
CLEAR_PLAIN = _plain(CLEAR_HTML)

# Обратная совместимость для импортов по старым именам.
WELCOME = WELCOME_HTML
ABOUT = ABOUT_HTML
INSTALL = INSTALL_HTML
GEMINI_KEY = GEMINI_KEY_HTML
HELP = HELP_HTML
