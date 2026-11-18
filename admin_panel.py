#!/usr/bin/env python3
"""Панель администратора Шелли: только для владельца этого бота.

Никаких чужих чатов, текстов сообщений и выводов команд: только служебная
статистика, события и управление сервисами на этом же VPS.
"""

import asyncio
import html
import json
import os
import subprocess
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from dotenv import dotenv_values

from . import telemetry
from .config import ADMIN_ID, TG_TOKEN, set_setting

CENTRAL_ENV = os.getenv("SHELLY_CENTRAL_ENV_FILE") or "/root/shelly/.env"
UNITS = ("shelly-tg.service", "shelly-test.service", "shelly-admin.service")

EVENT_LABELS = {
    "start": "👤 Новый пользователь зашёл в бота",
    "bot_created": "🤖 Создан бот через ссылку",
    "first_task": "🚀 Первая задача от пользователя",
    "task": "💬 Задача",
    "retry": "🔁 Переключение модели",
    "error": "⚠️ Ошибка агента",
    "confirm": "✅ Подтверждение опасной команды",
    "service": "🛠 Действие с сервисом",
}

bot = Bot(token=TG_TOKEN)
dp = Dispatcher(storage=MemoryStorage())


def is_owner(user_id):
    return bool(ADMIN_ID and int(user_id) == ADMIN_ID)


def keyboard(section="stats"):
    def btn(text, key, active=False):
        mark = "• " if active else ""
        return InlineKeyboardButton(text=mark + text, callback_data=f"panel:{key}")

    rows = [
        [btn("Статистика", "stats", section == "stats"), btn("События", "events", section == "events")],
        [btn("Сервисы", "services", section == "services"), btn("Управление", "control", section == "control")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def control_keyboard():
    rows = [
        [InlineKeyboardButton(text="Перезапустить shelly-tg", callback_data="ctl:restart-tg")],
        [InlineKeyboardButton(text="Перезапустить тестовый бот", callback_data="ctl:restart-test")],
        [InlineKeyboardButton(text="shelly-doctor", callback_data="ctl:doctor")],
        [InlineKeyboardButton(text="Терминал: вкл/выкл", callback_data="ctl:terminal")],
        [InlineKeyboardButton(text="Назад", callback_data="panel:control")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _ago(stamp):
    try:
        moment = datetime.fromisoformat(stamp)
    except Exception:
        return "—"
    seconds = max(0, int((datetime.now(timezone.utc) - moment).total_seconds()))
    if seconds < 60:
        return f"{seconds} с назад"
    if seconds < 3600:
        return f"{seconds // 60} мин назад"
    if seconds < 86400:
        return f"{seconds // 3600} ч назад"
    return f"{seconds // 86400} дн назад"


def stats_text():
    stats = telemetry.read_stats()
    users = stats.get("users", {})
    events = stats.get("events", {})

    day = 0
    for stamp in users.values():
        try:
            if (datetime.now(timezone.utc) - datetime.fromisoformat(stamp)).total_seconds() <= 86400:
                day += 1
        except Exception:
            continue

    lines = [
        "<b>Панель администратора</b>",
        "",
        f"Пользователей всего: <code>{len(users)}</code>",
        f"За сутки: <code>{day}</code>",
        f"Создано ботов: <code>{len(stats.get('bots', []))}</code>",
        "",
        "<b>События</b>",
    ]
    labels = {
        "start": "Заходы в бота",
        "bot_created": "Создано ботов",
        "first_task": "Первые задачи",
        "task": "Всего задач",
        "retry": "Переключений модели",
        "error": "Ошибок",
        "confirm": "Подтверждений",
        "service": "Действий с сервисами",
    }
    for key, label in labels.items():
        lines.append(f"{label}: <code>{events.get(key, 0)}</code>")
    lines.append("")
    lines.append(f"Последнее событие: {_ago(stats.get('last_event_at') or '')}")
    lines.append(f"Панель работает с: {_ago(stats.get('started_at') or '')}")
    lines.append("")
    lines.append("Тексты сообщений и вывод команд не сохраняются.")
    return "\n".join(lines)


def events_text(limit=12):
    entries = telemetry.read_events(limit)
    if not entries:
        return "<b>События</b>\n\nПока пусто."
    lines = ["<b>Последние события</b>", ""]
    for entry in entries:
        label = EVENT_LABELS.get(entry.get("event"), entry.get("event", "событие"))
        who = f" · ID {entry['user_id']}" if entry.get("user_id") else ""
        detail = f" · {html.escape(str(entry['detail']))}" if entry.get("detail") else ""
        lines.append(f"{html.escape(label)}{html.escape(who)}{detail} · {_ago(entry.get('ts', ''))}")
    return "\n".join(lines)


def services_text():
    lines = ["<b>Сервисы</b>", ""]
    for unit in UNITS:
        result = subprocess.run(
            ["systemctl", "is-active", unit], capture_output=True, text=True, timeout=10
        )
        state = result.stdout.strip() or "unknown"
        icon = "✅" if state == "active" else "⛔"
        lines.append(f"{icon} <code>{unit}</code> — {html.escape(state)}")
    uptime = subprocess.run(["uptime", "-p"], capture_output=True, text=True, timeout=10)
    lines.append("")
    lines.append(f"Время работы VPS: {html.escape(uptime.stdout.strip())}")
    lines.append(f"Сейчас: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return "\n".join(lines)


def control_text():
    cfg = dotenv_values(CENTRAL_ENV)
    enabled = cfg.get("SHELLY_TERMINAL_AUTOSTART", "1") != "0"
    state = "включён" if enabled else "выключен"
    return (
        "<b>Управление</b>\n\n"
        f"Автозапуск в терминале: <code>{state}</code>.\n\n"
        "Доступны только действия на этом VPS: перезапуск своих сервисов, "
        "проверка doctor и переключатель терминала. Чужие серверы и чаты недоступны."
    )


def panel_text(section):
    if section == "events":
        return events_text()
    if section == "services":
        return services_text()
    if section == "control":
        return control_text()
    return stats_text()


async def send_panel(chat_id, section="stats"):
    markup = control_keyboard() if section == "control" else keyboard(section)
    await bot.send_message(
        chat_id=chat_id,
        text=panel_text(section),
        parse_mode=ParseMode.HTML,
        reply_markup=markup,
        disable_web_page_preview=True,
    )


async def deny(chat_id):
    await bot.send_message(chat_id=chat_id, text="Панель доступна только владельцу этого бота.")


@dp.message(Command("start"))
@dp.message(Command("panel"))
async def cmd_panel(message: Message):
    if not is_owner(message.from_user.id):
        await deny(message.chat.id)
        return
    await send_panel(message.chat.id, "stats")


@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    if not is_owner(message.from_user.id):
        await deny(message.chat.id)
        return
    await send_panel(message.chat.id, "stats")


@dp.message(Command("events"))
async def cmd_events(message: Message):
    if not is_owner(message.from_user.id):
        await deny(message.chat.id)
        return
    await send_panel(message.chat.id, "events")


@dp.message(Command("services"))
async def cmd_services(message: Message):
    if not is_owner(message.from_user.id):
        await deny(message.chat.id)
        return
    await send_panel(message.chat.id, "services")


@dp.callback_query(F.data.startswith("panel:"))
async def on_panel(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    section = callback.data.split(":", 1)[1]
    await callback.answer()
    await send_panel(callback.message.chat.id, section)


def run_action(action):
    telemetry.record("service", detail=action)
    if action == "restart-tg":
        subprocess.run(["systemctl", "restart", "shelly-tg.service"], check=True, timeout=30)
        return "shelly-tg перезапущен."
    if action == "restart-test":
        subprocess.run(["systemctl", "restart", "shelly-test.service"], check=True, timeout=30)
        return "Тестовый бот перезапущен."
    if action == "doctor":
        env = dict(os.environ, SHELLY_ENV_FILE=CENTRAL_ENV)
        result = subprocess.run(
            ["/root/shelly/.venv/bin/shelly-doctor"],
            capture_output=True, text=True, timeout=150, env=env,
        )
        tail = "\n".join((result.stdout + result.stderr).splitlines()[-14:])
        return "Проверка выполнена:\n<pre>" + html.escape(tail) + "</pre>"
    if action == "terminal":
        cfg = dotenv_values(CENTRAL_ENV)
        enabled = cfg.get("SHELLY_TERMINAL_AUTOSTART", "1") != "0"
        set_setting("SHELLY_TERMINAL_AUTOSTART", "0" if enabled else "1", env_file=CENTRAL_ENV)
        return f"Автозапуск в терминале {'выключен' if enabled else 'включён'}."
    raise ValueError(action)


@dp.callback_query(F.data.startswith("ctl:"))
async def on_control(callback: CallbackQuery):
    if not is_owner(callback.from_user.id):
        await callback.answer("Только для владельца", show_alert=True)
        return
    action = callback.data.split(":", 1)[1]
    await callback.answer("Выполняю…")
    try:
        result = await asyncio.to_thread(run_action, action)
    except Exception as exc:
        result = f"Не получилось: {html.escape(str(exc))}"
    await bot.send_message(
        chat_id=callback.message.chat.id,
        text=result,
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )
    await send_panel(callback.message.chat.id, "control")


def format_event(entry):
    label = EVENT_LABELS.get(entry.get("event"), entry.get("event", "событие"))
    who = f" · ID {entry.get('user_id')}" if entry.get("user_id") else ""
    detail = f" · {entry['detail']}" if entry.get("detail") else ""
    return f"{label}{who}{detail}"


async def watch_events():
    offset = telemetry.read_offset()
    if offset is None:
        telemetry.write_offset(telemetry.size_of_events())
        offset = telemetry.size_of_events()

    while True:
        try:
            if not os.path.exists(telemetry.ADMIN_EVENTS_FILE):
                await asyncio.sleep(3)
                continue
            with open(telemetry.ADMIN_EVENTS_FILE, "rb") as fh:
                fh.seek(offset)
                chunk = fh.read()
                new_offset = fh.tell()
            if chunk:
                wanted = set(telemetry.notify_events())
                delivered = True
                for line in chunk.decode("utf-8", errors="replace").splitlines():
                    try:
                        entry = json.loads(line)
                    except Exception:
                        continue
                    if entry.get("event") in wanted:
                        try:
                            await bot.send_message(chat_id=ADMIN_ID, text=format_event(entry))
                        except Exception as exc:
                            delivered = False
                            print(f"admin watcher send: {exc}", flush=True)
                if delivered:
                    telemetry.write_offset(new_offset)
                    offset = new_offset
        except Exception as exc:
            print(f"admin watcher: {exc}", flush=True)
        await asyncio.sleep(3)


async def main():
    await bot.set_my_commands([
        BotCommand(command="panel", description="Панель администратора"),
        BotCommand(command="stats", description="Статистика"),
        BotCommand(command="events", description="Последние события"),
        BotCommand(command="services", description="Состояние сервисов"),
    ])
    asyncio.create_task(watch_events())
    await dp.start_polling(bot)


def run():
    asyncio.run(main())


if __name__ == "__main__":
    run()
