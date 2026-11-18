"""Локальная телеметрия Шелли: только служебные события, без текстов сообщений.

Файлы живут рядом с установкой и не попадают в git. Панель администратора читает
их с того же сервера; наружу ничего не отправляется.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from .config import (
    ADMIN_EVENTS_FILE, ADMIN_NOTIFY_EVENTS, ADMIN_OFFSET_FILE,
    ADMIN_STATS_FILE,
)

DEFAULT_STATS = {
    "started_at": datetime.now(timezone.utc).isoformat(),
    "users": {},
    "bots": [],
    "events": {},
    "once": {},
    "last_event_at": None,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _load():
    path = Path(ADMIN_STATS_FILE)
    if not path.exists():
        return json.loads(json.dumps(DEFAULT_STATS))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_STATS))
    for key, value in DEFAULT_STATS.items():
        data.setdefault(key, value)
    return data


def _save(stats):
    path = Path(ADMIN_STATS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def record(event, user_id=None, detail=None, once=False):
    """Записать служебное событие.

    `detail` должен быть безопасным: имя бота, класс ошибки, модель — но не текст
    пользовательского сообщения и не вывод команд.
    """
    if os.getenv("SHELLY_TELEMETRY_DISABLED") == "1":
        return False

    stats = _load()
    stamp = _now()
    uid = str(user_id) if user_id is not None else None

    if uid and uid not in stats["users"]:
        stats["users"][uid] = stamp

    key = f"{event}:{uid or ''}"
    if once and key in stats["once"]:
        return False
    if once:
        stats["once"][key] = stamp

    stats["events"][event] = stats["events"].get(event, 0) + 1
    if event == "bot_created" and detail:
        stats["bots"].append({"username": str(detail), "at": stamp})
        stats["bots"] = stats["bots"][-100:]
    stats["last_event_at"] = stamp
    _save(stats)

    entry = {"ts": stamp, "event": event, "user_id": uid, "detail": detail}
    events_path = Path(ADMIN_EVENTS_FILE)
    events_path.parent.mkdir(parents=True, exist_ok=True)
    with events_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    os.chmod(events_path, 0o600)
    return True


def read_stats():
    return _load()


def read_events(limit=10):
    path = Path(ADMIN_EVENTS_FILE)
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    out = []
    for line in lines[-limit:]:
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return list(reversed(out))


def notify_events():
    return [item.strip() for item in ADMIN_NOTIFY_EVENTS.split(",") if item.strip()]


def read_offset():
    path = Path(ADMIN_OFFSET_FILE)
    try:
        return int(path.read_text(encoding="utf-8").strip() or 0)
    except Exception:
        return None


def write_offset(offset):
    path = Path(ADMIN_OFFSET_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(int(offset)), encoding="utf-8")


def size_of_events():
    path = Path(ADMIN_EVENTS_FILE)
    return path.stat().st_size if path.exists() else 0
