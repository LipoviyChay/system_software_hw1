# sysapp — ДЗ №1 по системному ПО (контейнер + CI/CD + мониторинг)

**Генератор паролей** (FastAPI). Сервер генерирует криптостойкий пароль (модуль `secrets`) по заданным
параметрам (длина, заглавные, цифры, символы) и оценивает надёжность по энтропии. Пароли нигде не хранятся.
Клиенты тонкие: браузер (страница `/`) и Telegram-бот (`/pass [длина]`, `/stats`, `/health`) — вся логика на сервере.

| Что | Где |
|---|---|
| Приложение | `https://<имя>.onrender.com/` |
| API | `GET /api/password?length=16&upper=true&digits=true&symbols=true` |
| Health check | `https://<имя>.onrender.com/health` |
| **Мониторинг** | `https://<имя>.onrender.com/monitoring` (health, CPU, память, посещения и пароли в час) |
| Метрики Prometheus | `https://<имя>.onrender.com/metrics` |
| Артефакт сборки | GitHub → Actions → запуск → Artifacts → `sysapp-wheel` (хранится 90 дней) |
| Docker-образ | `ghcr.io/<user>/<repo>` (хранится постоянно) |

> Хостинг бесплатный (Render Free): после 15 минут без запросов контейнер засыпает,
> первый запрос после простоя может занять до ~1 минуты. Счётчики посещений при этом обнуляются.

## Структура

```
app/                    исходный код приложения (Python-пакет) и тесты
Dockerfile              описание контейнера (упаковывает собранный артефакт)
scripts/build.sh        скрипт сборки: зависимости -> тесты -> wheel
scripts/render-deploy.sh скрипт деплоя в Render
.github/workflows/      CI/CD-пайплайн
docker-compose.yml, monitoring/, scripts/deploy.sh, scripts/server-setup.sh
                        ДОПОЛНИТЕЛЬНО: полный стек (Prometheus + Grafana) для запуска на своём
                        сервере/компьютере, см. раздел в конце
```

## Как устроен CI/CD

Запускается при каждом push в `main`.

1. **build** — `scripts/build.sh`: зависимости, тесты (pytest), сборка артефакта — wheel `sysapp-*.whl`.
   Артефакт сохраняется в GitHub Actions (`upload-artifact`, 90 дней).
2. **docker** — скачивает *тот же* артефакт; `Dockerfile` устанавливает его в образ `python:3.12-slim`;
   образ пушится в `ghcr.io` с тегами `:<sha коммита>` и `:latest`.
3. **deploy** — `scripts/render-deploy.sh` дёргает deploy hook Render с параметром `imgURL`,
   и Render запускает именно образ этого коммита. Render сам ничего не собирает из исходников:
   в контейнер попадает ровно тот артефакт, который собрал пайплайн.

Откат: в Render → Manual Deploy → выбрать старый тег или перезапустить хук со старым `imgURL`.

## Мониторинг (внутри приложения)

Страница `/monitoring` (данные — `/api/monitoring`, JSON) показывает:
- **Health check** — статус и аптайм (`/health` — для внешних проверок);
- **Ресурсы** — CPU и память процесса приложения (psutil), память контейнера по cgroup;
- **Посещения и сгенерированные пароли** — за последний час, всего и по часам за 24 часа.

## Настройка с нуля (Render)

1. **GitHub:** создайте репозиторий, залейте проект:
   ```bash
   git init && git add . && git commit -m "init"
   git branch -M main
   git remote add origin https://github.com/<user>/<repo>.git
   git push -u origin main
   ```
   Вкладка **Actions** покажет первый прогон. Деплой в нём пропустится (секрета ещё нет) — это нормально.
2. **Сделайте образ публичным:** GitHub → ваш профиль → Packages → пакет → Package settings →
   Change visibility → Public. (Иначе Render не сможет его скачать без токена.)
3. **Render:** New → Web Service → *Deploy an existing image* → `ghcr.io/<user>/<repo>:latest`
   (имя в нижнем регистре) → тариф Free. В Settings → Health Check Path укажите `/health`.
4. **Deploy hook:** Render → ваш сервис → Settings → Deploy Hook → скопируйте URL.
   GitHub → Settings → Secrets and variables → Actions → New secret: `RENDER_DEPLOY_HOOK_URL`.
5. Сделайте любой коммит в `main` — пайплайн соберёт, запушит образ и обновит сервис.

Перед проверкой преподавателем откройте ссылку сами, чтобы контейнер проснулся.

## Дополнительно: полный стек на своём компьютере/сервере

`docker-compose.yml` поднимает приложение, Telegram-бота, Prometheus, node-exporter и Grafana
(дашборд подключается автоматически, `monitoring/`). Нужен файл `.env`:
```
IMAGE=ghcr.io/<user>/<repo>:latest
TELEGRAM_BOT_TOKEN=            # необязательно
GRAFANA_ADMIN_PASSWORD=change-me
```
Запуск: `docker compose up -d`. Приложение — порт 80, Grafana — 3000.
Для сервера с SSH в репозитории есть `scripts/server-setup.sh` и `scripts/deploy.sh`.
