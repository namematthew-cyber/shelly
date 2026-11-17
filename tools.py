"""Реестр инструментов Шелли. Инструмент ровно один: выполнение команд."""

import subprocess
from dataclasses import dataclass
from typing import Callable, Optional

from .config import COMMAND_TIMEOUT, DANGEROUS_PATTERNS, WORKDIR, setting
from .masking import mask


def setting_confirm_all():
    """Если включено, подтверждение требуется для любой команды."""
    return setting("SHELLY_CONFIRM_ALL", "0").lower() in ("1", "true", "yes", "да")


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable


def _cut(s: str, limit: int = 20000) -> str:
    s = s or ""
    return s if len(s) <= limit else s[:limit] + "\n...[вывод обрезан]"


def run_command(command: str, confirm: Optional[Callable] = None) -> dict:
    """Выполняет любую shell-команду от имени root."""
    if any(p in command.lower() for p in DANGEROUS_PATTERNS) or setting_confirm_all():
        if not confirm or not confirm(f"Выполнить опасную команду?\n  {mask(command)}"):
            return {
                "stdout": "",
                "stderr": "Отменено пользователем: опасная команда.",
                "exit_code": 126,
            }
    try:
        p = subprocess.run(
            command, shell=True, executable="/bin/bash", cwd=WORKDIR,
            capture_output=True, text=True, timeout=COMMAND_TIMEOUT,
            stdin=subprocess.DEVNULL,
        )
        return {
            "stdout": mask(_cut(p.stdout)),
            "stderr": mask(_cut(p.stderr)),
            "exit_code": p.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"Таймаут {COMMAND_TIMEOUT} секунд", "exit_code": 124}


TOOLS = [
    Tool(
        name="run_command",
        description=(
            "Выполняет любую shell-команду от имени root и возвращает stdout, "
            "stderr и код возврата. Единственный инструмент Шелли."
        ),
        parameters={
            "type": "OBJECT",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Полная команда для bash",
                }
            },
            "required": ["command"],
        },
        handler=run_command,
    ),
]

TOOL_MAP = {t.name: t for t in TOOLS}
