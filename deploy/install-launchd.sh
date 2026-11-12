#!/usr/bin/env bash
# Встановлює слухач як фоновий сервіс macOS (launchd): автозапуск при вході та перезапуск при падінні.
# Використання: ./deploy/install-launchd.sh            — встановити/перезапустити
#               ./deploy/install-launchd.sh uninstall  — видалити
set -euo pipefail

LABEL="com.electricity-notification"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
PY="$ROOT/.venv/bin/python"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true

if [[ "${1:-}" == "uninstall" ]]; then
  rm -f "$PLIST"
  echo "Видалено $LABEL"
  exit 0
fi

[[ -x "$PY" ]] || { echo "Немає $PY — спершу створіть venv (див. README)"; exit 1; }
[[ -f "$ROOT/.env" ]] || { echo "Немає $ROOT/.env — скопіюйте .env.example і заповніть"; exit 1; }
mkdir -p "$ROOT/logs" "$HOME/Library/LaunchAgents"

cat > "$PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key>
  <array><string>$PY</string><string>-m</string><string>power_notifier</string><string>run</string></array>
  <key>WorkingDirectory</key><string>$ROOT</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>ThrottleInterval</key><integer>30</integer>
  <key>StandardOutPath</key><string>$ROOT/logs/notifier.log</string>
  <key>StandardErrorPath</key><string>$ROOT/logs/notifier.log</string>
</dict>
</plist>
PLIST

launchctl bootstrap "gui/$(id -u)" "$PLIST"
echo "Запущено $LABEL. Лог: $ROOT/logs/notifier.log"
