#!/usr/bin/env bash
# Сборка: установка зависимостей -> тесты -> сборка артефакта (wheel) в dist/
set -euo pipefail
cd "$(dirname "$0")/.."

python -m pip install --upgrade pip
python -m pip install -e "app[dev]"

echo ">>> Тесты"
python -m pytest app

echo ">>> Сборка артефакта"
rm -rf dist
python -m build --wheel --outdir dist app
ls -l dist
