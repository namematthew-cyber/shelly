#!/usr/bin/env python3
"""Проверка установки Шелли: конфиг, права, доступность Telegram и Gemini."""

import asyncio
import os
import re
import stat
import sys

from aiogram import Bot
from google import genai
from google.genai import types

from .config import (
    ADMIN_ID, API_KEYS, ENV_FILE, LOG_PATH, MODELS, TG_TOKEN, WORKDIR,
)

OK = "[OK]"
WARN = "[!]"
FAIL = "[X]"


def check(label, condition, detail="", critical=True):
    mark = OK if condition else (FAIL if critical else WARN)
    print(f"{mark} {label}" + (f" — {detail}" if detail else ""))
    return bool(condition)


def check_config():
    print("\nКонфигурация")
    results = []

    results.append(check(
        "Файл .env найден",
        ENV_FILE.exists(),
        str(ENV_FILE) if ENV_FILE.exists() else "создай его из .env.example",
    ))

    if ENV_FILE.exists():
        mode = stat.S_IMODE(ENV_FILE.stat().st_mode)
        results.append(check(
            "Права на .env",
            not (mode & 0o077),
            oct(mode) + " (нужно 600)",
            critical=False,
        ))

    results.append(check(
        "Ключи Gemini заданы",
        bool(API_KEYS),
        f"{len(API_KEYS)} шт." if API_KEYS else "GEMINI_API_KEYS пуст",
    ))
    if API_KEYS:
        bad = [k for k in API_KEYS if not (k.startswith("AIza") or k.startswith("AQ."))]
        results.append(check(
            "Формат ключей Gemini",
            not bad,
            "все похожи на ключи" if not bad else f"{len(bad)} не похожи на AIzaSy... или AQ...",
            critical=False,
        ))

    token_ok = bool(re.fullmatch(r"\d{8,12}:[A-Za-z0-9_-]{30,}", TG_TOKEN or ""))
    results.append(check("Токен Telegram задан и выглядит верно", token_ok))
    results.append(check("SHELLY_ADMIN_ID указан", ADMIN_ID > 0, str(ADMIN_ID or "не задан")))
    results.append(check("Рабочая директория существует", os.path.isdir(WORKDIR), WORKDIR))

    log_dir = os.path.dirname(LOG_PATH) or "."
    results.append(check(
        "Журнал доступен для записи",
        os.access(log_dir, os.W_OK),
        log_dir,
        critical=False,
    ))
    return all(results)


async def check_services():
    print("\nСервисы")
    results = []

    if TG_TOKEN:
        bot = Bot(token=TG_TOKEN)
        try:
            async with asyncio.timeout(15):
                me = await bot.get_me()
            results.append(check("Telegram API отвечает", True, f"@{me.username} ({me.first_name})"))
        except Exception as e:
            results.append(check("Telegram API отвечает", False, type(e).__name__))
        finally:
            await bot.session.close()
    else:
        results.append(check("Telegram API отвечает", False, "нет токена"))

    if API_KEYS:
        try:
            client = genai.Client(api_key=API_KEYS[0])
            def ask():
                return client.models.generate_content(
                    model=MODELS[0],
                    contents=types.Content(
                        role="user", parts=[types.Part(text="Ответь одним словом: ок")]
                    ),
                    config=types.GenerateContentConfig(temperature=0),
                )
            async with asyncio.timeout(30):
                response = await asyncio.to_thread(ask)
            text = "".join(
                p.text for p in (response.candidates[0].content.parts if response.candidates else [])
                if getattr(p, "text", None)
            )
            results.append(check("Gemini отвечает", bool(text), MODELS[0]))
        except Exception as e:
            results.append(check("Gemini отвечает", False, f"{type(e).__name__}: {str(e)[:90]}"))
    else:
        results.append(check("Gemini отвечает", False, "нет ключа"))

    return all(results)


def main():
    print("Шелли — проверка установки")
    config_ok = check_config()
    services_ok = asyncio.run(check_services())

    print("\nИтог:", "всё готово к работе" if config_ok and services_ok else "есть проблемы, исправь их выше")
    print("Подробнее о получении ключа: /keys в боте или раздел README.")
    return 0 if config_ok and services_ok else 1


if __name__ == "__main__":
    sys.exit(main())
