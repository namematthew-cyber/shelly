#!/usr/bin/env python3
"""Шелли — AI-агент для сервера в терминале (harness)."""

import sys
import itertools
import threading

from .agent import Agent, human_error
from .config import ACCENT, DIM, GREETING_PROMPT, paint
from .masking import mask


# Ввод в SSH может приходить с битыми последовательностями — не роняем чат из-за этого
if hasattr(sys.stdin, "reconfigure"):
    sys.stdin.reconfigure(encoding="utf-8", errors="replace")

_SPIN = itertools.cycle("⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏")
_spinner_stop = None
_spinner_thread = None
_spinner_width = 0


def label():
    return paint("Шелли", ACCENT) + ":"


def say(text):
    """Сообщение Шелли с воздухом сверху и снизу."""
    print()
    print(label() + " " + mask(text), flush=True)
    print()


def _think(stop):
    global _spinner_width
    while not stop.is_set():
        text = f"Шелли думает {next(_SPIN)}"
        # Сначала затираем предыдущий кадр ровно по его видимой ширине,
        # затем рисуем новый — чтобы не оставалось хвостов от старых символов.
        sys.stdout.write("\r" + " " * _spinner_width + "\r" + paint(text, DIM))
        sys.stdout.flush()
        _spinner_width = len(text)
        stop.wait(0.08)


def thinking_start():
    global _spinner_stop, _spinner_thread, _spinner_width
    if not sys.stdout.isatty():
        return
    sys.stdout.write("\n")
    sys.stdout.flush()
    _spinner_width = 0
    _spinner_stop = threading.Event()
    _spinner_thread = threading.Thread(target=_think, args=(_spinner_stop,), daemon=True)
    _spinner_thread.start()


def thinking_stop():
    global _spinner_stop, _spinner_thread, _spinner_width
    if _spinner_stop is None:
        return
    _spinner_stop.set()
    _spinner_thread.join()
    sys.stdout.write("\r" + " " * _spinner_width + "\r")
    sys.stdout.flush()
    _spinner_stop = None
    _spinner_thread = None
    _spinner_width = 0


def confirm(text):
    """Запрос подтверждения на опасное действие."""
    print()
    print(paint(text, DIM))
    if not sys.stdin.isatty():
        return False
    try:
        answer = input(paint("Подтвердить? [y/N]: ", DIM)).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    return answer in {"y", "yes", "да", "д"}


def on_tool(name, args):
    detail = ", ".join(f"{k}={v!r}" for k, v in args.items())
    if len(detail) > 80:
        detail = detail[:77] + "..."
    say(paint(f"вызываю {name}({detail})", DIM))


def build_agent():
    return Agent(
        confirm=confirm,
        on_thinking_start=thinking_start,
        on_thinking_stop=thinking_stop,
        on_tool=on_tool,
    )


def main():
    print()
    print("Хотите запустить эвристическую матрицу?")
    print()
    print(paint("  1.", ACCENT) + " Да")
    print(paint("  2.", DIM) + " Нет")
    print()
    try:
        choice = input(paint("Выбор [1]: ", DIM)).strip()
    except (EOFError, KeyboardInterrupt):
        choice = "2"
    if choice not in {"", "1"}:
        return

    try:
        agent = build_agent()
    except Exception as e:
        say(f"не удалось запустить матрицу: {e}")
        return

    # Приветствие тоже генерирует агент — он сам собирает данные командой
    try:
        greeting = agent.send(GREETING_PROMPT)
        say(greeting)
    except Exception as e:
        say(f"не удалось получить приветствие: {e}")

    while True:
        try:
            user_text = input(paint("ты> ", DIM)).strip()
        except (EOFError, KeyboardInterrupt):
            say("До связи. Без меня тут скучно будет.")
            break

        if not user_text:
            continue
        if user_text.lower() in {"выход", "exit", "quit", "q"}:
            say("До связи. Без меня тут скучно будет.")
            break

        try:
            say(agent.send(user_text))
        except Exception as e:
            say(human_error(e))


if __name__ == "__main__":
    main()
