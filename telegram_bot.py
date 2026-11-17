#!/usr/bin/env python3
"""Telegram-адаптер Шелли: тонкий слой над общим Agent.

Бот отвечает всем: у каждого пользователя свой агент и история. Команды доступны только
в собственной установке; подтверждать их может лишь владелец (SHELLY_ADMIN_ID).
Опасные команды подтверждаются inline-кнопками Да/Нет.
Анимированный черновик показывает «Шелли думает», команды и ретраи идут отдельным
редактируемым статусом, а в чат уходит только итоговый rich-ответ.
"""

import asyncio
import html
import json
import logging
import os
from collections import OrderedDict
from pathlib import Path
import random
import re
import secrets
import threading
import time
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.methods import GetManagedBotToken
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    CopyTextButton,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    ManagedBotUpdated,
    Message,
)

from .agent import Agent, human_error
from .config import (
    ADMIN_ID, CONFIRM_TIMEOUT, TG_TOKEN,
    THINK_EMOJI_CHAR, THINK_EMOJI_ID,
)
from .masking import mask
from . import texts

logger = logging.getLogger("shelly.tg")

if not TG_TOKEN or not ADMIN_ID:
    raise RuntimeError("Проверь SHELLY_TG_TOKEN и SHELLY_ADMIN_ID в .env")

bot = Bot(token=TG_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

main_loop = None
_bot_username = None
_manage_bots = False
_managed = {}
_agents = OrderedDict()
_AGENT_LIMIT = 200
_user_locks = {}
_pending = {}
_pending_lock = threading.Lock()
MAX_MESSAGE = 4096
RICH_LIMIT = 30000
# Команда должна быть видна не «долю секунды», а хотя бы столько.
MIN_COMMAND_SEC = 1.5

# Предложенные имена для ботов пользователей: храним, чтобы не повторить имя
# даже после перезапуска сервиса.
BOT_NAMES_PATH = Path(__file__).with_name(".bot_names.json")
_names_lock = threading.Lock()
_bot_names = {"users": {}, "used": []}


def _load_bot_names():
    try:
        data = json.loads(BOT_NAMES_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict) and isinstance(data.get("users"), dict):
            _bot_names["users"] = {str(k): v for k, v in data["users"].items()}
            _bot_names["used"] = list(data.get("used") or [])
    except FileNotFoundError:
        pass
    except Exception as e:
        logger.warning("Не прочитал реестр имён ботов: %s", e)


def _save_bot_names():
    BOT_NAMES_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = BOT_NAMES_PATH.with_name(BOT_NAMES_PATH.name + ".tmp")
    tmp.write_text(json.dumps(_bot_names, ensure_ascii=False), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, BOT_NAMES_PATH)


def suggested_bot_username(user_id=None) -> str:
    """Имя вида shelly_ai_<цифры>_bot, уникальное в пределах установки."""
    key = str(user_id) if user_id is not None else "anon"
    with _names_lock:
        if not _bot_names["users"] and not _bot_names["used"]:
            _load_bot_names()
        existing = _bot_names["users"].get(key)
        if existing:
            return existing
        used = set(_bot_names["used"])
        while True:
            digits = f"{int(time.time())}{secrets.randbelow(1_000_000):06d}"
            name = f"shelly_ai_{digits}_bot"
            if len(name) <= 32 and name not in used:
                break
        _bot_names["users"][key] = name
        _bot_names["used"].append(name)
        _save_bot_names()
        return name


_load_bot_names()

_CUSTOM_EMOJI = f'<tg-emoji emoji-id="{THINK_EMOJI_ID}">{html.escape(THINK_EMOJI_CHAR)}</tg-emoji>'
# Никаких своих точек: только эмодзи и надпись, анимацию рисует сам Telegram.
THINK_HTML = f"<tg-thinking>{_CUSTOM_EMOJI} Шелли думает</tg-thinking>"
THINK_PLAIN = f"{THINK_EMOJI_CHAR} Шелли думает"


def _short_command(command):
    text = " ".join(mask(command or "").split())
    return text[:180] + "…" if len(text) > 180 else text


def exec_html(command):
    return f"<tg-thinking>{_CUSTOM_EMOJI} Выполняю: {html.escape(_short_command(command))}</tg-thinking>"


def retry_html(model):
    return f"<tg-thinking>{_CUSTOM_EMOJI} Проверяю модель {html.escape(str(model))}…</tg-thinking>"


def exec_plain(command):
    return f"{THINK_EMOJI_CHAR} Выполняю: {_short_command(command)}"


def status_html(command=None, retry_model=None):
    """Обычное сообщение со статусом: редактируется и остаётся в чате до ответа."""
    if command:
        return f"{_CUSTOM_EMOJI} Выполняю: {html.escape(_short_command(command))}"
    if retry_model:
        return f"{_CUSTOM_EMOJI} Проверяю модель {html.escape(str(retry_model))}…"
    return f"{_CUSTOM_EMOJI} Шелли думает"


def is_owner(user_id):
    return bool(ADMIN_ID and user_id == ADMIN_ID)


def get_agent(user_id):
    """Свой агент на пользователя: история не смешивается, команды — только у владельца."""
    key = int(user_id)
    active = _agents.get(key)
    if active is not None:
        _agents.move_to_end(key)
        return active
    owner = is_owner(key)
    active = Agent(confirm=tg_confirm if owner else None, public=not owner)
    _agents[key] = active
    if len(_agents) > _AGENT_LIMIT:
        _agents.popitem(last=False)
    return active


def user_lock(user_id):
    lock = _user_locks.get(user_id)
    if lock is None:
        lock = _user_locks[user_id] = asyncio.Lock()
    return lock


def rich_html(text):
    """Безопасный dynamic-текст без лишней подписи и самодельных украшений."""
    safe = html.escape(mask(text or ""))
    limit = RICH_LIMIT - 50  # запас на <p> и экранирование
    if len(safe) > limit:
        safe = safe[:limit] + "…"
    return f"<p>{safe.replace('\n', '<br/>')}</p>"


def chunks(text, size=RICH_LIMIT):
    text = (text or "").strip() or "(команда выполнена, слов не нашлось)"
    parts = []
    while text:
        if len(text) <= size:
            parts.append(text)
            break
        cut = text.rfind("\n", 0, size)
        if cut < size // 2:
            cut = size
        parts.append(text[:cut].rstrip())
        text = text[cut:].lstrip()
    return parts


async def stream_agent(prompt, active_agent):
    """Один запрос к агенту: статусы приходят через колбэки, в чат идёт только итог."""
    try:
        return await asyncio.to_thread(active_agent.send, prompt, True, None)
    except Exception as e:
        logger.exception("Ошибка агента: %s", e)
        return human_error(e)


async def send_rich(chat_id, text):
    for part in chunks(text):
        try:
            await bot.send_rich_message(
                chat_id=chat_id,
                rich_message=InputRichMessage(html=rich_html(part)),
            )
        except Exception as e:
            logger.exception("Не удалось отправить rich-сообщение: %s", e)
            await bot.send_message(chat_id=str(chat_id), text=html.escape(mask(part)))


def create_bot_url(user_id=None):
    """Ссылка на создание своего бота через Bot Management Mode.

    Если режим не включён, ведём в BotFather — пользователь создаст бота вручную.
    """
    if not _manage_bots or not _bot_username:
        return "https://t.me/BotFather"
    name = suggested_bot_username(user_id)
    return f"https://t.me/newbot/{_bot_username}/{name}?name=Shelly"


def _inline_keyboard(rows, user_id=None):
    buttons = []
    for row in rows:
        line = []
        for kind, value, label in row:
            if kind == "nav":
                line.append(InlineKeyboardButton(text=label, callback_data=f"nav:{value}"))
            elif kind == "copy":
                line.append(InlineKeyboardButton(
                    text=label, copy_text=CopyTextButton(text=value),
                ))
            elif kind == "url":
                line.append(InlineKeyboardButton(text=label, url=value))
            elif kind == "create":
                line.append(InlineKeyboardButton(text=label, url=create_bot_url(user_id)))
            elif kind == "prompt":
                line.append(InlineKeyboardButton(
                    text=label, switch_inline_query_current_chat=value,
                ))
            else:
                raise ValueError(f"Неизвестный тип кнопки: {kind}")
        buttons.append(line)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


WELCOME_IMAGE = Path(__file__).with_name("assets") / "welcome.png"

STATIC_PAGES = {
    "menu": (texts.WELCOME_HTML, texts.WELCOME_PLAIN, texts.WELCOME_BUTTONS),
    "about": (texts.ABOUT_HTML, texts.ABOUT_PLAIN, texts.ABOUT_BUTTONS),
    "install": (texts.INSTALL_HTML, texts.INSTALL_PLAIN, texts.INSTALL_BUTTONS),
    "connect": (texts.CONNECT_HTML, texts.CONNECT_PLAIN, texts.CONNECT_BUTTONS),
    "keys": (texts.GEMINI_KEY_HTML, texts.GEMINI_KEY_PLAIN, texts.GEMINI_KEY_BUTTONS),
    "help": (texts.HELP_HTML, texts.HELP_PLAIN, texts.HELP_BUTTONS),
    "examples": (texts.EXAMPLES_HTML, texts.EXAMPLES_PLAIN, texts.EXAMPLES_BUTTONS),
    "security": (texts.SECURITY_HTML, texts.SECURITY_PLAIN, texts.SECURITY_BUTTONS),
    "clear": (texts.CLEAR_HTML, texts.CLEAR_PLAIN, texts.CLEAR_BUTTONS),
}


async def send_page(chat_id, page, user_id=None):
    """Статические страницы — обычные сообщения с HTML и inline-кнопками."""
    markup, plain, rows = STATIC_PAGES[page]
    keyboard = _inline_keyboard(rows, user_id)

    # Первое сообщение — с инфографикой; текст уходит в подпись к фото.
    if page == "menu" and WELCOME_IMAGE.is_file():
        try:
            return await bot.send_photo(
                chat_id=chat_id,
                photo=FSInputFile(WELCOME_IMAGE),
                caption=markup,
                parse_mode=ParseMode.HTML,
                reply_markup=keyboard,
            )
        except Exception as e:
            logger.exception("Не удалось отправить картинку приветствия: %s", e)

    try:
        return await bot.send_message(
            chat_id=chat_id,
            text=markup,
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )
    except Exception as e:
        logger.exception("HTML-сообщение недоступно, шлю простой текст: %s", e)
        return await bot.send_message(
            chat_id=chat_id,
            text=plain,
            reply_markup=keyboard,
            disable_web_page_preview=True,
        )


class StreamView:
    """Один запрос: все статусы идут в один анимированный rich-черновик."""

    def __init__(self, message):
        self.message = message
        self.chat_id = message.chat.id
        self.draft_id = random.randint(1, 2_147_483_647)
        self.use_rich = True
        self.status_message = None
        self.last_command_at = None

    def _push_sync(self, markup):
        """Доставляем статус до запуска команды: быстрая команда не должна его перегнать."""
        if main_loop is None:
            return
        coro = self._push_draft(markup) if self.use_rich else self._push_plain(markup)
        future = asyncio.run_coroutine_threadsafe(coro, main_loop)
        try:
            future.result(timeout=5)
        except Exception as e:
            logger.debug("Статус не доставлен: %s", e)

    async def start(self):
        try:
            await self._push_draft(THINK_HTML)
        except Exception as e:
            self.use_rich = False
            logger.info("Rich-черновик недоступен, шлю обычный статус: %s", e)
            await self._push_plain(status_html())

    def _command_left(self):
        if self.last_command_at is None:
            return 0.0
        return max(0.0, MIN_COMMAND_SEC - (time.monotonic() - self.last_command_at))

    def set_executing(self, name, args):
        command = _short_command((args or {}).get("command", ""))
        self.last_command_at = time.monotonic()
        self._push_sync(exec_html(command) if self.use_rich else status_html(command=command))

    def set_done(self, name=None, args=None):
        # Статус команды не сбрасываем: быстрая команда иначе видна доли секунды.
        return None

    def set_retry(self, model):
        self._push_sync(retry_html(model) if self.use_rich else status_html(retry_model=model))

    async def hold_command(self):
        """Не отправлять итог раньше, чем команда побыла на экране."""
        left = self._command_left()
        if left > 0:
            await asyncio.sleep(left)

    async def _push_draft(self, markup):
        # Один draft_id = Telegram анимирует переход между статусами.
        await bot.send_rich_message_draft(
            chat_id=self.chat_id,
            draft_id=self.draft_id,
            rich_message=InputRichMessage(html=markup),
        )

    async def _push_plain(self, text):
        try:
            if self.status_message is None:
                self.status_message = await bot.send_message(
                    chat_id=self.chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_notification=True,
                )
            else:
                await bot.edit_message_text(
                    text=text,
                    chat_id=str(self.chat_id),
                    message_id=self.status_message.message_id,
                    parse_mode=ParseMode.HTML,
                )
        except Exception as e:
            logger.debug("Статус не обновлён: %s", e)

    async def close(self):
        if self.status_message is None:
            return
        try:
            await bot.delete_message(
                chat_id=str(self.chat_id),
                message_id=self.status_message.message_id,
            )
        except Exception as e:
            logger.debug("Не удалось удалить статус: %s", e)


async def ask_rich(message, prompt, view=None, active_agent=None):
    """Один запрос: статус в чате, в ответ уходит только итог."""
    view = view or StreamView(message)
    answer = await stream_agent(prompt, active_agent)
    await view.hold_command()
    await view.close()
    await send_rich(view.chat_id, answer)


async def ask(message, prompt):
    user_id = message.from_user.id
    async with user_lock(user_id):
        active_agent = get_agent(user_id)
        view = StreamView(message)
        await view.start()
        active_agent.on_tool = view.set_executing
        active_agent.on_tool_done = view.set_done
        active_agent.on_retry = view.set_retry
        try:
            await ask_rich(message, prompt, view, active_agent)
        finally:
            active_agent.on_tool = None
            active_agent.on_tool_done = None
            active_agent.on_retry = None


def _split_confirm(text):
    lines = (text or "").split("\n", 1)
    title = lines[0].strip() or "Нужно подтверждение"
    command = mask(lines[1].strip()) if len(lines) > 1 else ""
    return title, command


def confirm_rich(text):
    title, command = _split_confirm(text)
    return (
        f"<h2>{html.escape(title)}</h2>"
        f"<pre><code>{html.escape(command)}</code></pre>"
        "<footer>Решение действует только для этой команды</footer>"
    )


def confirm_plain(text, status=""):
    title, command = _split_confirm(text)
    prefix = f"{status} " if status else ""
    return f"<b>{html.escape(prefix + title)}</b>\n\n<pre>{html.escape(command)}</pre>"


def tg_confirm(text):
    """Подтверждение из потока агента: отправляем кнопки и ждём ответа."""
    loop = main_loop
    if loop is None:
        return False

    token = uuid.uuid4().hex[:8]
    event = threading.Event()
    box = {}
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ Да", callback_data=f"cfm:yes:{token}"),
        InlineKeyboardButton(text="⛔ Нет", callback_data=f"cfm:no:{token}"),
    ]])

    future = asyncio.run_coroutine_threadsafe(
        bot.send_rich_message(
            chat_id=str(ADMIN_ID),
            rich_message=InputRichMessage(html=confirm_rich(text)),
            reply_markup=keyboard,
        ),
        loop,
    )
    try:
        msg = future.result(timeout=20)
    except Exception as e:
        logger.warning("Не удалось отправить запрос подтверждения: %s", e)
        return False

    with _pending_lock:
        _pending[token] = (event, box, msg.chat.id, msg.message_id)

    done = event.wait(timeout=CONFIRM_TIMEOUT)
    with _pending_lock:
        _pending.pop(token, None)

    answer = box.get("answer") == "yes"
    if answer:
        label = "✅ Подтверждено"
    elif done:
        label = "⛔ Отменено"
    else:
        label = "⏱ Таймаут — отменила"
    asyncio.run_coroutine_threadsafe(
        bot.edit_message_text(
            text=confirm_plain(text, label),
            chat_id=str(msg.chat.id),
            message_id=msg.message_id,
            parse_mode=ParseMode.HTML,
            reply_markup=None,
        ),
        loop,
    )
    return bool(done and answer)


@dp.callback_query(F.data.startswith("cfm:"))
async def on_confirm(callback: CallbackQuery):
    # Подтверждать команды может только владелец сервера.
    if not is_owner(callback.from_user.id):
        await callback.answer("Это не для тебя.", show_alert=True)
        return

    _, answer, token = callback.data.split(":", 2)
    with _pending_lock:
        entry = _pending.get(token)
    if not entry:
        await callback.answer("Запрос уже закрыт.", show_alert=True)
        return

    event, box, _, _ = entry
    box["answer"] = answer
    event.set()
    await callback.answer("Приняла." if answer == "yes" else "Отклонила.")


async def handle_managed_bot(info):
    """Пользователь создал бота по нашей ссылке — выдаём токен и следующий шаг."""
    user = info.user
    new_bot = info.bot_user
    try:
        token = await bot(GetManagedBotToken(user_id=new_bot.id))
    except Exception as e:
        logger.exception("Не удалось получить токен созданного бота: %s", e)
        await bot.send_message(
            chat_id=user.id,
            text="Бот создан, но токен получить не вышло. Напиши /start и попробуй ещё раз.",
        )
        return

    _managed[user.id] = {"username": new_bot.username, "token": token}
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text="Перейти в бота", url=f"https://t.me/{new_bot.username}",
    )]])
    await bot.send_message(
        chat_id=user.id,
        text=texts.bot_created_html(new_bot.username, token),
        parse_mode=ParseMode.HTML,
        reply_markup=keyboard,
        disable_web_page_preview=True,
    )


@dp.managed_bot()
async def on_managed_bot(event: ManagedBotUpdated):
    await handle_managed_bot(event)


@dp.callback_query(F.data.startswith("nav:"))
async def on_nav(callback: CallbackQuery):
    page = callback.data.split(":", 1)[1]

    if page == "close":
        await callback.answer("Закрыла.")
        if callback.message:
            try:
                await bot.delete_message(
                    chat_id=callback.message.chat.id,
                    message_id=callback.message.message_id,
                )
            except Exception as e:
                logger.debug("Не удалось удалить меню: %s", e)
        return

    entry = STATIC_PAGES.get(page)
    if not entry:
        await callback.answer("Такой страницы нет.", show_alert=True)
        return

    await callback.answer()
    await send_page(callback.message.chat.id, page, callback.from_user.id)

    # Навигация не должна засорять чат: старая страница уезжает.
    if callback.message:
        try:
            await bot.delete_message(
                chat_id=callback.message.chat.id,
                message_id=callback.message.message_id,
            )
        except Exception as e:
            logger.debug("Не удалось удалить предыдущую страницу: %s", e)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    # Только приветствие: агент запускается по первой реальной задаче.
    await send_page(message.chat.id, "menu", message.from_user.id)


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    await send_page(message.chat.id, "menu", message.from_user.id)


@dp.message(Command("about"))
async def cmd_about(message: Message):
    await send_page(message.chat.id, "about", message.from_user.id)


@dp.message(Command("install"))
async def cmd_install(message: Message):
    await send_page(message.chat.id, "install", message.from_user.id)


@dp.message(Command("connect"))
async def cmd_connect(message: Message):
    await send_page(message.chat.id, "connect", message.from_user.id)


@dp.message(Command("keys"))
async def cmd_keys(message: Message):
    await send_page(message.chat.id, "keys", message.from_user.id)


@dp.message(Command("examples"))
async def cmd_examples(message: Message):
    await send_page(message.chat.id, "examples", message.from_user.id)


@dp.message(Command("security"))
async def cmd_security(message: Message):
    await send_page(message.chat.id, "security", message.from_user.id)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    user_id = message.from_user.id
    async with user_lock(user_id):
        _agents.pop(user_id, None)
    await send_page(message.chat.id, "clear", message.from_user.id)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    await send_page(message.chat.id, "help", message.from_user.id)


@dp.message(F.text)
async def on_text(message: Message):
    if message.text.startswith("/"):
        return
    await ask(message, message.text)


async def main():
    global main_loop, _bot_username, _manage_bots
    main_loop = asyncio.get_running_loop()

    me = await bot.get_me()
    _bot_username = me.username
    _manage_bots = bool(getattr(me, "can_manage_bots", False))
    if not _manage_bots:
        logger.warning(
            "Bot Management Mode выключен: включите его в BotFather (https://t.me/Botfather?startapp), "
            "иначе ссылка создаст бота через BotFather без автоматического токена"
        )
    logger.info("Шелли в Telegram: @%s, статус в чате, итог через rich messages", me.username)

    await bot.set_my_commands([
        BotCommand(command="start", description="Приветствие и меню"),
        BotCommand(command="menu", description="Открыть меню заново"),
        BotCommand(command="about", description="Что такое Шелли"),
        BotCommand(command="install", description="Как установить на свой сервер"),
        BotCommand(command="connect", description="Как подключить свой бот"),
        BotCommand(command="keys", description="Как получить ключ Gemini"),
        BotCommand(command="examples", description="Готовые задачи"),
        BotCommand(command="security", description="Как защищены секреты"),
        BotCommand(command="clear", description="Очистить контекст"),
        BotCommand(command="help", description="Справка"),
    ])

    try:
        # Явно просим managed_bot: без этого апдейт о созданном боте может не прийти.
        await dp.start_polling(
            bot,
            allowed_updates=["message", "callback_query", "managed_bot"],
        )
    finally:
        await bot.session.close()


def run():
    """Синхронная точка входа для console_script и systemd."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        force=True,
    )
    asyncio.run(main())


if __name__ == "__main__":
    run()
