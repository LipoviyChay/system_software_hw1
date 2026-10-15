#!/usr/bin/env bash
# Деплой на сервере: скачать образ, перезапустить контейнеры, проверить health.
# Переменные (IMAGE и др.) лежат в .env рядом с docker-compose.yml.
set -euo pipefail
cd "$(dirname "$0")/.."

docker compose pull
docker compose up -d --remove-orphans

echo ">>> Проверка health..."
for i in $(seq 1 20); do
  if curl -fsS http://localhost/health; then
    echo
    echo "Деплой успешен"
    docker image prune -f >/dev/null
    exit 0
  fi
  sleep 3
done

echo "Приложение не ответило на /health" >&2
docker compose logs --tail=50 app
exit 1
