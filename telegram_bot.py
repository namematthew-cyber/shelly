#!/usr/bin/env python3
"""Telegram-адаптер Шелли: тонкий слой над общим Agent.

Доступ настраивается через SHELLY_ADMIN_ID.
Опасные команды подтверждаются inline-кнопками Да/Нет.
Анимированный черновик показывает «Шелли думает», команды и ретраи идут отдельным
редактируемым статусом, а в чат уходит только итоговый rich-ответ.
"""

import asyncio
import html
import logging
import random
import re
import threading
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
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

agent = None
main_loop = None
_busy = asyncio.Lock()
_pending = {}
_pending_lock = threading.Lock()
MAX_MESSAGE = 4096
RICH_LIMIT = 30000

_CUSTOM_EMOJI = f'<tg-emoji emoji-id="{THINK_EMOJI_ID}">{html.escape(THINK_EMOJI_CHAR)}</tg-emoji>'
# Никаких своих точек: только эмодзи и надпись, анимацию рисует сам Telegram.
THINK_HTML = f"<tg-thinking>{_CUSTOM_EMOJI} Шелли думает</tg-thinking>"
THINK_PLAIN = f"{THINK_EMOJI_CHAR} Шелли думает"


def _short_command(command):
    text = " ".join(mask(command or "").split())
    return text[:180] + "…" if len(text) > 180 else text


def exec_html(command):
    return f"<tg-thinking>{_CUSTOM_EMOJI} Выполняю: {html.escape(_short_command(command))}</tg-thinking>"


def exec_plain(command):
    return f"{THINK_EMOJI_CHAR} Выполняю: {_short_command(command)}"


def status_html(command=None, retry_model=None):
    """Обычное сообщение со статусом: редактируется и остаётся в чате до ответа."""
    if command:
        return f"{_CUSTOM_EMOJI} Выполняю: {html.escape(_short_command(command))}"
    if retry_model:
        return f"{_CUSTOM_EMOJI} Проверяю модель {html.escape(str(retry_model))}…"
    return f"{_CUSTOM_EMOJI} Шелли думает"


def allowed(user_id):
    return bool(ADMIN_ID and user_id == ADMIN_ID)


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


async def stream_agent(prompt):
    """Один запрос к агенту: статусы приходят через колбэки, в чат идёт только итог."""
    try:
        return await asyncio.to_thread(agent.send, prompt, True, None)
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


def _inline_keyboard(rows):
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
            elif kind == "prompt":
                line.append(InlineKeyboardButton(
                    text=label, switch_inline_query_current_chat=value,
                ))
            else:
                raise ValueError(f"Неизвестный тип кнопки: {kind}")
        buttons.append(line)
    return InlineKeyboardMarkup(inline_keyboard=buttons)


STATIC_PAGES = {
    "menu": (texts.WELCOME_HTML, texts.WELCOME_PLAIN, texts.WELCOME_BUTTONS),
    "about": (texts.ABOUT_HTML, texts.ABOUT_PLAIN, texts.ABOUT_BUTTONS),
    "install": (texts.INSTALL_HTML, texts.INSTALL_PLAIN, texts.INSTALL_BUTTONS),
    "keys": (texts.GEMINI_KEY_HTML, texts.GEMINI_KEY_PLAIN, texts.GEMINI_KEY_BUTTONS),
    "help": (texts.HELP_HTML, texts.HELP_PLAIN, texts.HELP_BUTTONS),
    "examples": (texts.EXAMPLES_HTML, texts.EXAMPLES_PLAIN, texts.EXAMPLES_BUTTONS),
    "security": (texts.SECURITY_HTML, texts.SECURITY_PLAIN, texts.SECURITY_BUTTONS),
    "clear": (texts.CLEAR_HTML, texts.CLEAR_PLAIN, texts.CLEAR_BUTTONS),
}


async def send_page(chat_id, page):
    """Статические страницы — обычные сообщения с HTML и inline-кнопками."""
    markup, plain, rows = STATIC_PAGES[page]
    keyboard = _inline_keyboard(rows)
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
    """Один запрос: анимированный «думает» + одно сообщение для команд и ретраев."""

    def __init__(self, message):
        self.message = message
        self.chat_id = message.chat.id
        self.draft_id = random.randint(1, 2_147_483_647)
        self.use_rich = True
        self.status_message = None
        self.status_lock = asyncio.Lock()

    def _push_sync(self, text):
        """Доставляем статус до запуска команды: быстрая команда не должна его перегнать."""
        if main_loop is None:
            return
        future = asyncio.run_coroutine_threadsafe(self._push_status(text), main_loop)
        try:
            future.result(timeout=5)
        except Exception as e:
            logger.debug("Статус не доставлен: %s", e)

    async def start(self):
        try:
            await bot.send_rich_message_draft(
                chat_id=self.chat_id,
                draft_id=self.draft_id,
                rich_message=InputRichMessage(html=THINK_HTML),
            )
        except Exception as e:
            self.use_rich = False
            logger.info("Анимированный черновик недоступен, шлю обычный статус: %s", e)
            await self._push_status(status_html())

    def set_executing(self, name, args):
        command = _short_command((args or {}).get("command", ""))
        self._push_sync(status_html(command=command))

    def set_done(self, name=None, args=None):
        # «Думает» уже крутится в черновике, а команда пусть остаётся видимой —
        # возврат к Thinking в обычном сообщении давал два одинаковых статуса.
        return None

    def set_retry(self, model):
        self._push_sync(status_html(retry_model=model))

    async def _push_status(self, text):
        async with self.status_lock:
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


async def ask_rich(message, prompt, view=None):
    """Один запрос: статус в чате, в ответ уходит только итог."""
    view = view or StreamView(message)
    answer = await stream_agent(prompt)
    await view.close()
    await send_rich(view.chat_id, answer)


async def ask(message, prompt):
    async with _busy:
        view = StreamView(message)
        await view.start()
        agent.on_tool = view.set_executing
        agent.on_tool_done = view.set_done
        agent.on_retry = view.set_retry
        try:
            await ask_rich(message, prompt, view)
        finally:
            agent.on_tool = None
            agent.on_tool_done = None
            agent.on_retry = None


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
    if not allowed(callback.from_user.id):
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


@dp.callback_query(F.data.startswith("nav:"))
async def on_nav(callback: CallbackQuery):
    if not allowed(callback.from_user.id):
        await callback.answer("Это не для тебя.", show_alert=True)
        return

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
    await send_page(callback.message.chat.id, page)

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
    if not allowed(message.from_user.id):
        return
    # Только приветствие: агент запускается по первой реальной задаче.
    await send_page(message.chat.id, "menu")


@dp.message(Command("menu"))
async def cmd_menu(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "menu")


@dp.message(Command("about"))
async def cmd_about(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "about")


@dp.message(Command("install"))
async def cmd_install(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "install")


@dp.message(Command("keys"))
async def cmd_keys(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "keys")


@dp.message(Command("examples"))
async def cmd_examples(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "examples")


@dp.message(Command("security"))
async def cmd_security(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "security")


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    if not allowed(message.from_user.id):
        return
    global agent
    async with _busy:
        agent = Agent(confirm=tg_confirm)
    await send_page(message.chat.id, "clear")


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_page(message.chat.id, "help")


@dp.message(F.text)
async def on_text(message: Message):
    if not allowed(message.from_user.id) or message.text.startswith("/"):
        return
    await ask(message, message.text)


async def main():
    global agent, main_loop
    main_loop = asyncio.get_running_loop()
    agent = Agent(confirm=tg_confirm)

    await bot.set_my_commands([
        BotCommand(command="start", description="Приветствие и меню"),
        BotCommand(command="menu", description="Открыть меню заново"),
        BotCommand(command="about", description="Что такое Шелли"),
        BotCommand(command="install", description="Как установить на свой сервер"),
        BotCommand(command="keys", description="Как получить ключ Gemini"),
        BotCommand(command="examples", description="Готовые задачи"),
        BotCommand(command="security", description="Как защищены секреты"),
        BotCommand(command="clear", description="Очистить контекст"),
        BotCommand(command="help", description="Справка"),
    ])

    me = await bot.get_me()
    logger.info("Шелли в Telegram: @%s, статус в чате, итог через rich messages", me.username)

    try:
        await dp.start_polling(bot)
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
