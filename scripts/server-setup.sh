#!/usr/bin/env bash
# Однократная подготовка сервера (Ubuntu/Debian). Запускать под root или через sudo.
set -euo pipefail

# 1. Docker + compose-плагин
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi

# 2. Фаервол: SSH, приложение (80), Grafana (3000)
if command -v ufw >/dev/null; then
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 3000/tcp
  ufw --force enable
fi

# 3. Папка деплоя и права
DEPLOY_USER="${SUDO_USER:-$USER}"
usermod -aG docker "$DEPLOY_USER"
mkdir -p "/home/$DEPLOY_USER/sysapp"
chown -R "$DEPLOY_USER":"$DEPLOY_USER" "/home/$DEPLOY_USER/sysapp"

echo "Готово. Перелогиньтесь по SSH, чтобы заработала группа docker."
