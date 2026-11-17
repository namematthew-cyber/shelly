#!/usr/bin/env python3
"""Telegram-адаптер Шелли: тонкий слой над общим Agent.

Доступ только у одного пользователя (SHELLY_ADMIN_ID).
Опасные команды подтверждаются inline-кнопками Да/Нет.
Ответы стримятся через sendRichMessageDraft и закрепляются sendRichMessage.
"""

import asyncio
import html
import logging
import random
import re
import threading
import time
import uuid

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputRichMessage,
    Message,
)

from .agent import Agent, human_error
from .config import (
    ADMIN_ID, CONFIRM_TIMEOUT, LONG_REQUEST_AFTER, TG_TOKEN,
    THINK_EMOJI_CHAR, THINK_EMOJI_ID,
)
from .masking import mask
from .texts import (
    ABOUT_HTML, ABOUT_PLAIN, CLEAR_HTML, CLEAR_PLAIN,
    GEMINI_KEY_HTML, GEMINI_KEY_PLAIN, HELP_HTML, HELP_PLAIN,
    INSTALL_HTML, INSTALL_PLAIN, WELCOME_HTML, WELCOME_PLAIN,
)

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
FLUSH_INTERVAL = 0.25

_CUSTOM_EMOJI = f'<tg-emoji emoji-id="{THINK_EMOJI_ID}">{html.escape(THINK_EMOJI_CHAR)}</tg-emoji>'
# Никаких своих точек: только эмодзи и надпись, анимацию рисует сам Telegram.
THINK_HTML = f"<tg-thinking>Шелли думает {_CUSTOM_EMOJI}</tg-thinking>"
THINK_PLAIN = f"Шелли думает {THINK_EMOJI_CHAR}"


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


def make_buffer():
    """Разделяемый между потоком агента и event loop буфер нарастающего текста."""
    data = {"text": ""}
    lock = threading.Lock()

    def on_delta(delta):
        with lock:
            data["text"] += delta

    return data, lock, on_delta


async def pump(data, lock, sender):
    """Раз в FLUSH_INTERVAL обновляем черновик; после порога — и обычное сообщение."""
    started = time.monotonic()
    last = None
    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        with lock:
            text = data["text"]
        elapsed = time.monotonic() - started
        # Долгий запрос без текста должен всё-таки показать, что бот жив.
        if text == last and elapsed < LONG_REQUEST_AFTER:
            continue
        try:
            await sender(text, elapsed)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.debug("Стрим остановлен: %s", e)
            return
        last = text


async def stream_agent(prompt, data, lock, on_delta, sender):
    task = asyncio.create_task(pump(data, lock, sender))
    try:
        answer = await asyncio.to_thread(agent.send, prompt, True, on_delta)
    except Exception as e:
        logger.exception("Ошибка агента: %s", e)
        answer = human_error(e)
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    return answer


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


async def send_rich_html(chat_id, markup, plain):
    """Статичные тексты Шелли: сначала rich, при неудаче — простой текст."""
    try:
        return await bot.send_rich_message(
            chat_id=chat_id,
            rich_message=InputRichMessage(html=markup),
        )
    except Exception as e:
        logger.exception("Rich-сообщение недоступно, отправляю простой текст: %s", e)
        return await bot.send_message(chat_id=str(chat_id), text=plain)


STATIC_PAGES = {
    "about": (ABOUT_HTML, ABOUT_PLAIN),
    "install": (INSTALL_HTML, INSTALL_PLAIN),
    "keys": (GEMINI_KEY_HTML, GEMINI_KEY_PLAIN),
    "help": (HELP_HTML, HELP_PLAIN),
}


async def ask_rich(message, prompt, draft_id):
    chat_id = message.chat.id
    data, lock, on_delta = make_buffer()
    fallback = None
    fallback_text = None
    draft_text = None

    async def partial(text, elapsed=0):
        nonlocal fallback, fallback_text, draft_text

        # Rich-draft живёт ~30 секунд. Если запрос затянулся, параллельно держим
        # обычное сообщение, которое можно редактировать сколь угодно долго.
        if elapsed >= LONG_REQUEST_AFTER and fallback is None:
            try:
                fallback = await message.answer(THINK_PLAIN)
            except Exception as e:
                logger.debug("Не удалось создать keepalive-сообщение: %s", e)

        if fallback is not None and text and text != fallback_text:
            try:
                await bot.edit_message_text(
                    text=html.escape(mask(text)),
                    chat_id=str(chat_id),
                    message_id=fallback.message_id,
                )
                fallback_text = text
            except Exception as e:
                logger.debug("Keepalive-редактирование пропущено: %s", e)

        if text and text != draft_text:
            await bot.send_rich_message_draft(
                chat_id=chat_id,
                draft_id=draft_id,
                rich_message=InputRichMessage(html=rich_html(text)),
            )
            draft_text = text

    answer = await stream_agent(prompt, data, lock, on_delta, partial)

    if fallback is not None:
        try:
            await bot.delete_message(chat_id=str(chat_id), message_id=fallback.message_id)
        except Exception as e:
            logger.debug("Не удалось удалить keepalive-сообщение: %s", e)

    await send_rich(chat_id, answer)


async def ask_plain(message, prompt):
    """Фолбэк, если rich-drafts недоступны: редактируем обычное сообщение."""
    placeholder = await message.answer(THINK_PLAIN)
    chat_id = placeholder.chat.id
    data, lock, on_delta = make_buffer()

    async def partial(text, elapsed=0):
        await bot.edit_message_text(
            text=html.escape(mask(text)),
            chat_id=str(chat_id),
            message_id=placeholder.message_id,
        )

    answer = await stream_agent(prompt, data, lock, on_delta, partial)

    parts = chunks(answer, MAX_MESSAGE)
    try:
        await bot.edit_message_text(
            text=html.escape(mask(parts[0])),
            chat_id=str(chat_id),
            message_id=placeholder.message_id,
        )
        for part in parts[1:]:
            await bot.send_message(chat_id=str(chat_id), text=html.escape(mask(part)))
    except Exception as e:
        logger.exception("Не удалось отправить ответ: %s", e)
        await bot.send_message(chat_id=str(chat_id), text=f"Не смогла отправить ответ: {e}")


async def ask(message, prompt):
    async with _busy:
        chat_id = message.chat.id
        draft_id = random.randint(1, 2_147_483_647)
        try:
            await bot.send_rich_message_draft(
                chat_id=chat_id,
                draft_id=draft_id,
                rich_message=InputRichMessage(html=THINK_HTML),
            )
        except Exception as e:
            logger.info("Rich draft недоступен, использую обычные сообщения: %s", e)
            await ask_plain(message, prompt)
            return
        await ask_rich(message, prompt, draft_id)


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
    entry = STATIC_PAGES.get(page)
    if not entry:
        await callback.answer("Такой страницы нет.", show_alert=True)
        return

    markup, plain = entry
    await callback.answer()
    await send_rich_html(callback.message.chat.id, markup, plain)


@dp.message(Command("start"))
async def cmd_start(message: Message):
    if not allowed(message.from_user.id):
        return
    # Только приветствие: агент запускается по первой реальной задаче.
    await send_rich_html(message.chat.id, WELCOME_HTML, WELCOME_PLAIN)


@dp.message(Command("about"))
async def cmd_about(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_rich_html(message.chat.id, ABOUT_HTML, ABOUT_PLAIN)


@dp.message(Command("install"))
async def cmd_install(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_rich_html(message.chat.id, INSTALL_HTML, INSTALL_PLAIN)


@dp.message(Command("keys"))
async def cmd_keys(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_rich_html(message.chat.id, GEMINI_KEY_HTML, GEMINI_KEY_PLAIN)


@dp.message(Command("clear"))
async def cmd_clear(message: Message):
    if not allowed(message.from_user.id):
        return
    global agent
    async with _busy:
        agent = Agent(confirm=tg_confirm)
    await send_rich_html(message.chat.id, CLEAR_HTML, CLEAR_PLAIN)


@dp.message(Command("help"))
async def cmd_help(message: Message):
    if not allowed(message.from_user.id):
        return
    await send_rich_html(message.chat.id, HELP_HTML, HELP_PLAIN)


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
        BotCommand(command="start", description="Приветствие и быстрый старт"),
        BotCommand(command="about", description="Что такое Шелли"),
        BotCommand(command="install", description="Как установить на свой сервер"),
        BotCommand(command="keys", description="Как получить ключ Gemini"),
        BotCommand(command="clear", description="Очистить контекст"),
        BotCommand(command="help", description="Справка"),
    ])

    me = await bot.get_me()
    logger.info("Шелли в Telegram: @%s, доступ только для %s, стриминг через rich messages", me.username, ADMIN_ID)

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
