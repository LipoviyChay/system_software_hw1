#!/usr/bin/env bash
# Деплой в Render: просим Render запустить конкретный образ из реестра.
# Нужны переменные: RENDER_DEPLOY_HOOK_URL (секрет) и IMAGE (например ghcr.io/user/repo:abc1234)
set -euo pipefail

if [ -z "${RENDER_DEPLOY_HOOK_URL:-}" ]; then
  echo "RENDER_DEPLOY_HOOK_URL не задан - деплой пропущен."
  exit 0
fi
: "${IMAGE:?нужна переменная IMAGE}"

IMG_ENC=$(jq -rn --arg u "$IMAGE" '$u|@uri')
curl -fsS "${RENDER_DEPLOY_HOOK_URL}&imgURL=${IMG_ENC}"
echo
echo "Деплой запущен: $IMAGE"
