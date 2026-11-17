#!/usr/bin/env bash
# Установка Шелли: окружение, .env и (опционально) systemd-сервис.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PARENT="$(dirname "$DIR")"
VENV="$DIR/.venv"
ENV_FILE="$DIR/.env"

if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
    AMBER=$'\033[1;38;5;178m'
    DIM=$'\033[2m'
    GREEN=$'\033[32m'
    RED=$'\033[31m'
    RESET=$'\033[0m'
    ANIMATE=1
else
    AMBER='' DIM='' GREEN='' RED='' RESET=''
    ANIMATE=0
fi

FRAMES=('⠋' '⠙' '⠹' '⠸' '⠼' '⠴' '⠦' '⠧' '⠇' '⠏')

section() { printf '\n  %s──  %s  ──%s\n\n' "$DIM" "$1" "$RESET"; }
step()    { printf '  %s◆%s  %s\n' "$AMBER" "$RESET" "$1"; }
ok()      { printf '  %s✓%s  %s\n' "$GREEN" "$RESET" "$1"; }
fail()    { printf '  %s✗%s  %s\n' "$RED" "$RESET" "$1"; }
hint()    { printf '  %s%s%s\n' "$DIM" "$1" "$RESET"; }

run_step() {
    local label="$1"; shift
    local out pid rc=0 i=0 frame
    out="$(mktemp)"
    if [ "$ANIMATE" = 1 ]; then
        "$@" >"$out" 2>&1 &
        pid=$!
        while kill -0 "$pid" 2>/dev/null; do
            frame="${FRAMES[$((i % ${#FRAMES[@]}))]}"
            printf '\r  %s%s%s  %s' "$AMBER" "$frame" "$RESET" "$label"
            sleep 0.08
            i=$((i + 1))
        done
        if wait "$pid"; then rc=0; else rc=$?; fi
        printf '\r'
    else
        if "$@" >"$out" 2>&1; then rc=0; else rc=$?; fi
    fi
    if [ "$rc" -eq 0 ]; then
        ok "$label"
    else
        fail "$label"
        cat "$out" >&2
    fi
    rm -f "$out"
    return "$rc"
}

valid_utf8() {
    printf '%s' "$1" | "$PYTHON" -c 'import sys; sys.stdin.buffer.read().decode("utf-8")' 2>/dev/null
}

printf '\n'
printf '  %sS H E L L Y%s  %s· установка%s\n' "$AMBER" "$RESET" "$DIM" "$RESET"
printf '  %s────────────────────────────────%s\n' "$DIM" "$RESET"
printf '\n'
printf '  Каталог  %s\n' "$DIR"
printf '\n'

PYTHON="${PYTHON:-python3}"
if ! command -v "$PYTHON" >/dev/null 2>&1; then
    fail "Не найден $PYTHON"
    exit 1
fi

section "Окружение"
if [ ! -d "$VENV" ]; then
    run_step "Создаю виртуальное окружение" "$PYTHON" -m venv "$VENV"
else
    ok "Виртуальное окружение уже есть"
fi
run_step "Устанавливаю пакет" "$VENV/bin/pip" install -q -e "$DIR"

section "Настройки"
overwrite=''
if [ -f "$ENV_FILE" ]; then
    read -rp "  ${AMBER}→${RESET} Файл .env уже есть. Перезаписать? [y/N]: " overwrite
    case "$overwrite" in
        y|Y|yes|да) ;;
        *) ok "Оставляю существующий .env"; overwrite='' ;;
    esac
fi

if [ ! -f "$ENV_FILE" ] || [[ "${overwrite:-}" == "y" || "${overwrite:-}" == "Y" || "${overwrite:-}" == "да" ]]; then
    read -rsp "  ${AMBER}→${RESET} Ключ(и) Gemini через запятой: " keys; echo
    read -rsp "  ${AMBER}→${RESET} Токен Telegram-бота: " token; echo
    read -rp  "  ${AMBER}→${RESET} Твой Telegram ID: " admin
    read -rp  "  ${AMBER}→${RESET} Как тебя зовут: " name
    read -rp  "  ${AMBER}→${RESET} Ссылка на репозиторий проекта [необязательно]: " project_url

    name="${name:-хозяин}"
    if ! valid_utf8 "$name"; then
        hint "Имя записалось с битыми символами — ставлю Shelly"
        name="Shelly"
    fi

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
    ok "Записал $ENV_FILE (права 600)"
fi

if [[ "${1:-}" == "--service" ]]; then
    section "Сервис"
    UNIT=/etc/systemd/system/shelly-tg.service
    step "Устанавливаю systemd-сервис"
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
    ok "Сервис shelly-tg запущен"
    hint "Статус: systemctl status shelly-tg"
fi

section "Проверка"
"$VENV/bin/shelly-doctor" || true

printf '\n'
printf '  %sГотово%s\n' "$AMBER" "$RESET"
printf '  %s────────────────────────────────%s\n' "$DIM" "$RESET"
printf '  терминал   %s\n' "$VENV/bin/shelly"
printf '  Telegram   %s\n' "$VENV/bin/shelly-tg"
printf '  проверка   %s\n' "$VENV/bin/shelly-doctor"
printf '\n'
