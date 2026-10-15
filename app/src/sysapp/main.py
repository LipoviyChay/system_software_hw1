"""Бэкенд (тонкий клиент-сервер: вся логика тут, клиенты - браузер и Telegram-бот).

Мониторинг встроен в само приложение: /health, /monitoring (страница) и /api/monitoring (JSON).
Формат Prometheus (/metrics) оставлен для полного стека из docker-compose.
"""
import os
import threading
import time
from collections import deque

import psutil
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

VERSION = os.getenv("APP_VERSION", "dev")
START_TIME = time.time()

app = FastAPI(title="sysapp", version=VERSION)

# --- метрики Prometheus ---
VISITS = Counter("app_visits_total", "Количество посещений главной страницы")
APP_UP = Gauge("app_up", "1, если приложение работоспособно")
APP_UP.set(1)
UPTIME = Gauge("app_uptime_seconds", "Время работы приложения, сек")
UPTIME.set_function(lambda: time.time() - START_TIME)

# --- счётчик посещений (в памяти; при перезапуске/засыпании контейнера обнуляется) ---
_lock = threading.Lock()
_visit_times: deque = deque()  # метки времени посещений за последние 24 часа
_total_visits = 0

_proc = psutil.Process()
_proc.cpu_percent(interval=None)  # "прогрев": первый вызов всегда возвращает 0
psutil.cpu_percent(interval=None)


def _register_visit() -> int:
    global _total_visits
    now = time.time()
    with _lock:
        _total_visits += 1
        _visit_times.append(now)
        while _visit_times and _visit_times[0] < now - 24 * 3600:
            _visit_times.popleft()
        VISITS.inc()
        return _total_visits


def _visits_last_hour() -> int:
    cutoff = time.time() - 3600
    with _lock:
        return sum(1 for t in _visit_times if t >= cutoff)


def _visits_by_hour() -> list:
    """Посещения по часам за последние 24 часа (последний элемент - текущий час)."""
    now = time.time()
    buckets = [0] * 24
    with _lock:
        for t in _visit_times:
            ago = int((now - t) // 3600)
            if 0 <= ago < 24:
                buckets[23 - ago] += 1
    return buckets


def _cgroup_memory_mb():
    """Память контейнера по cgroup (если доступно), иначе None."""
    for path in ("/sys/fs/cgroup/memory.current",
                 "/sys/fs/cgroup/memory/memory.usage_in_bytes"):
        try:
            with open(path) as f:
                return round(int(f.read().strip()) / 1024 / 1024, 1)
        except (OSError, ValueError):
            continue
    return None


def collect_monitoring() -> dict:
    return {
        "health": "OK",
        "version": VERSION,
        "uptime_seconds": int(time.time() - START_TIME),
        "resources": {
            "process_cpu_percent": _proc.cpu_percent(interval=None),
            "process_memory_mb": round(_proc.memory_info().rss / 1024 / 1024, 1),
            "container_memory_mb": _cgroup_memory_mb(),
            "host_cpu_percent": psutil.cpu_percent(interval=None),
        },
        "visits": {
            "total": _total_visits,
            "last_hour": _visits_last_hour(),
            "by_hour_last_24h": _visits_by_hour(),
        },
    }


@app.get("/health")
def health():
    """Health check: если отвечает - приложение живо."""
    return {"status": "ok", "version": VERSION}


@app.get("/metrics")
def metrics():
    """Метрики в формате Prometheus."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/api/monitoring")
def api_monitoring():
    return collect_monitoring()


@app.get("/api/stats")
def stats():
    """Краткая статистика для бота. Посещение НЕ засчитывает."""
    return {
        "visits": _total_visits,
        "uptime_seconds": int(time.time() - START_TIME),
        "version": VERSION,
    }


@app.get("/monitoring", response_class=HTMLResponse)
def monitoring_page():
    return MONITORING_HTML


@app.get("/", response_class=HTMLResponse)
def index():
    n = _register_visit()
    return f"""<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>sysapp</title>
<style>body{{font-family:system-ui,sans-serif;max-width:560px;margin:15vh auto;text-align:center}}
small{{color:#777}}</style></head>
<body><h1>Привет! 👋</h1>
<p>Вы посетитель № <b>{n}</b></p>
<p><small>версия: {VERSION}</small></p>
<p><a href="/monitoring">мониторинг</a> · <a href="/health">/health</a> · <a href="/metrics">/metrics</a></p>
</body></html>"""


MONITORING_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Мониторинг sysapp</title>
<style>
body{font-family:system-ui,sans-serif;max-width:720px;margin:24px auto;padding:0 16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.card{border:1px solid #8884;border-radius:10px;padding:12px}
.card b{display:block;font-size:1.5rem;margin-top:4px}
.up{color:#1a9a3a}.down{color:#d33}
.bars{display:flex;align-items:flex-end;gap:3px;height:90px;margin-top:8px}
.bars div{flex:1;background:#4a8af4;min-height:2px;border-radius:2px}
small{color:#888}
</style></head><body>
<h1>Мониторинг</h1>
<div class="grid">
 <div class="card">Health<b id="health">…</b></div>
 <div class="card">Аптайм<b id="uptime">…</b></div>
 <div class="card">CPU процесса<b id="cpu">…</b></div>
 <div class="card">Память процесса<b id="mem">…</b></div>
 <div class="card">Посещений за час<b id="hour">…</b></div>
 <div class="card">Посещений всего<b id="total">…</b></div>
</div>
<h3>Посещения по часам (последние 24 ч)</h3>
<div class="bars" id="bars"></div>
<p><small>Обновляется каждые 5 секунд. Счётчики хранятся в памяти и обнуляются при перезапуске.</small></p>
<script>
async function tick(){
  try{
    const d = await (await fetch('/api/monitoring')).json();
    const h = document.getElementById('health');
    h.textContent = d.health; h.className = 'up';
    uptime.textContent = d.uptime_seconds + ' с';
    cpu.textContent = d.resources.process_cpu_percent + ' %';
    mem.textContent = d.resources.process_memory_mb + ' МБ';
    hour.textContent = d.visits.last_hour;
    total.textContent = d.visits.total;
    const arr = d.visits.by_hour_last_24h, max = Math.max(1, ...arr);
    bars.innerHTML = arr.map(v => `<div title="${v}" style="height:${v/max*100}%"></div>`).join('');
  }catch(e){
    const h = document.getElementById('health'); h.textContent='DOWN'; h.className='down';
  }
}
tick(); setInterval(tick, 5000);
</script></body></html>"""
