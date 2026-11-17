"""Маскировка секретов в выводе команд, логах и сообщениях.

Задача: ключ Gemini или токен бота, оказавшись в выводе `cat .env`, не должен
уехать ни в Gemini, ни в Telegram, ни в аудит-лог.
"""

import re

from .config import setting

ENABLED = setting("SHELLY_MASK_SECRETS", "1").lower() in ("1", "true", "yes", "да")

# Важен порядок: сначала присваивания в .env, потом сами значения.
PATTERNS = [
    (
        re.compile(r"(?i)\b([A-Z_]*(?:KEY|TOKEN|SECRET|PASSWORD|PASSWD)[A-Z_]*)\s*=\s*[^\s'\"#]+"),
        r"\1=***",
    ),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"), "<ПРИВАТНЫЙ КЛЮЧ СКРЫТ>"),
    (re.compile(r"AIza[0-9A-Za-z_\-]{30,}"), "AIza***"),
    (re.compile(r"\bAQ\.[A-Za-z0-9_\-]{40,}\b"), "AQ.***"),
    (re.compile(r"\b\d{8,12}:[A-Za-z0-9_\-]{30,}\b"), "<ТОКЕН ТЕЛЕГРАМ>***"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AKIA***"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"), "gh***"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"), "sk-***"),
]


def mask(value):
    """Заменяет похожие на секреты фрагменты на заглушки."""
    if not value or not ENABLED:
        return value
    text = str(value)
    for pattern, replacement in PATTERNS:
        text = pattern.sub(replacement, text)
    return text
