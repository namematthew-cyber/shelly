#!/usr/bin/env bash
# Установка Шелли: окружение, .env и (опционально) systemd-сервис.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(dirname "$DIR")"
VENV="$DIR/.venv"
ENV_FILE="$DIR/.env"

echo "Шелли — установка"
echo "Каталог: $DIR"

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    echo "Не найден $PYTHON" >&2
    exit 1
fi

if [ ! -d "$VENV" ]; then
    echo "Создаю виртуальное окружение..."
    "$PYTHON" -m venv "$VENV"
fi
"$VENV/bin/pip" install -q -e "$DIR"

if [ -f "$ENV_FILE" ]; then
    read -rp "Файл .env уже есть. Перезаписать? [y/N]: " overwrite
    case "$overwrite" in
        y|Y|yes|да) ;;
        *) echo "Оставляю существующий .env" ;;
    esac
fi

if [ ! -f "$ENV_FILE" ] || [[ "${overwrite:-}" == "y" || "${overwrite:-}" == "Y" || "${overwrite:-}" == "да" ]]; then
    read -rsp "Ключ(и) Gemini через запятую: " keys; echo
    read -rsp "Токен Telegram-бота: " token; echo
    read -rp "Твой Telegram ID: " admin
    read -rp "Как тебя зовут: " name
    name="${name:-хозяин}"
    read -rp "Ссылка на репозиторий проекта [необязательно]: " project_url

    umask 077
    cat > "$ENV_FILE" <<EOF
GEMINI_API_KEYS=$keys
SHELLY_TG_TOKEN=$token
SHELLY_ADMIN_ID=$admin
SHELLY_USER_NAME=$name
SHELLY_WORKDIR=$PARENT
SHELLY_PROJECT_URL=$project_url
SHELLY_MASK_SECRETS=1
EOF
    echo "Записал $ENV_FILE (права 600)"
fi

if [[ "${1:-}" == "--service" ]]; then
    UNIT=/etc/systemd/system/shelly-tg.service
    echo "Устанавливаю systemd-сервис $UNIT"
    cat > /tmp/shelly-tg.service.tmp <<EOF
[Unit]
Description=Shelly Telegram assistant
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$PARENT
Environment=PYTHONPATH=$PARENT
ExecStart=$VENV/bin/shelly-tg
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
# Консервативный харденинг: не мешает admin-командам, но закрывает часть атак
UMask=0077
PrivateTmp=true
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX

[Install]
WantedBy=multi-user.target
EOF
    if [ "$(id -u)" -eq 0 ]; then
        mv /tmp/shelly-tg.service.tmp "$UNIT"
    else
        sudo mv /tmp/shelly-tg.service.tmp "$UNIT"
    fi
    systemctl daemon-reload
    systemctl enable --now shelly-tg.service
    echo "Готово: systemctl status shelly-tg"
fi

echo "Проверяю установку..."
"$VENV/bin/shelly-doctor" || true

echo "Установка завершена."
echo "  Терминал:  $VENV/bin/shelly"
echo "  Telegram:  $VENV/bin/shelly-tg"
echo "  Проверка:  $VENV/bin/shelly-doctor"
