"""Генератор паролей - тонкий клиент-сервер.

Вся логика (генерация, оценка надёжности) на сервере; клиенты - браузер и Telegram-бот.
Пароли нигде не хранятся и не логируются.
Мониторинг встроен в приложение: /health, /monitoring, /api/monitoring (+ /metrics для Prometheus).
"""
import math
import os
import secrets
import string
import threading
import time
from collections import deque

import psutil
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, generate_latest

VERSION = os.getenv("APP_VERSION", "dev")
START_TIME = time.time()

app = FastAPI(title="sysapp - генератор паролей", version=VERSION)

# --- метрики Prometheus ---
VISITS_METRIC = Counter("app_visits_total", "Количество посещений главной страницы")
GENERATED_METRIC = Counter("app_passwords_generated_total", "Сколько паролей сгенерировано")
APP_UP = Gauge("app_up", "1, если приложение работоспособно")
APP_UP.set(1)
UPTIME = Gauge("app_uptime_seconds", "Время работы приложения, сек")
UPTIME.set_function(lambda: time.time() - START_TIME)


class EventCounter:
    """Считает события: всего, за последний час и по часам за сутки (в памяти)."""

    def __init__(self):
        self._lock = threading.Lock()
        self._times = deque()
        self.total = 0

    def add(self):
        now = time.time()
        with self._lock:
            self.total += 1
            self._times.append(now)
            while self._times and self._times[0] < now - 24 * 3600:
                self._times.popleft()

    def last_hour(self) -> int:
        cutoff = time.time() - 3600
        with self._lock:
            return sum(1 for t in self._times if t >= cutoff)

    def by_hour(self) -> list:
        """24 значения, последнее - текущий час."""
        now = time.time()
        buckets = [0] * 24
        with self._lock:
            for t in self._times:
                ago = int((now - t) // 3600)
                if 0 <= ago < 24:
                    buckets[23 - ago] += 1
        return buckets


visits = EventCounter()
generated = EventCounter()

_proc = psutil.Process()
_proc.cpu_percent(interval=None)  # "прогрев": первый вызов всегда возвращает 0
psutil.cpu_percent(interval=None)


# --- логика генерации ---
def make_password(length: int, upper: bool, digits: bool, symbols: bool):
    groups = [string.ascii_lowercase]
    if upper:
        groups.append(string.ascii_uppercase)
    if digits:
        groups.append(string.digits)
    if symbols:
        groups.append("!@#$%^&*()-_=+[]{};:,.?")
    pool = "".join(groups)
    # по одному символу из каждой выбранной группы + остальное из общего набора
    chars = [secrets.choice(g) for g in groups]
    chars += [secrets.choice(pool) for _ in range(length - len(chars))]
    secrets.SystemRandom().shuffle(chars)
    entropy = length * math.log2(len(pool))
    return "".join(chars), round(entropy, 1)


def strength_label(entropy: float) -> str:
    if entropy < 40:
        return "слабый"
    if entropy < 60:
        return "средний"
    if entropy < 80:
        return "хороший"
    return "отличный"


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
            "total": visits.total,
            "last_hour": visits.last_hour(),
            "by_hour_last_24h": visits.by_hour(),
        },
        "passwords": {
            "total": generated.total,
            "last_hour": generated.last_hour(),
            "by_hour_last_24h": generated.by_hour(),
        },
    }


# --- API ---
@app.get("/health")
def health():
    """Health check: если отвечает - приложение живо."""
    return {"status": "ok", "version": VERSION}


@app.get("/api/password")
def api_password(
    length: int = Query(16, ge=6, le=64),
    upper: bool = True,
    digits: bool = True,
    symbols: bool = True,
):
    """Сгенерировать пароль. Считается в метрику, но нигде не сохраняется."""
    password, entropy = make_password(length, upper, digits, symbols)
    generated.add()
    GENERATED_METRIC.inc()
    return {"password": password, "length": length,
            "entropy_bits": entropy, "strength": strength_label(entropy)}


@app.get("/api/stats")
def stats():
    """Краткая статистика для бота. Ничего не засчитывает."""
    return {
        "visits": visits.total,
        "passwords_generated": generated.total,
        "uptime_seconds": int(time.time() - START_TIME),
        "version": VERSION,
    }


@app.get("/api/monitoring")
def api_monitoring():
    return collect_monitoring()


@app.get("/metrics")
def metrics():
    """Метрики в формате Prometheus."""
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# --- страницы ---
@app.get("/", response_class=HTMLResponse)
def index():
    visits.add()
    VISITS_METRIC.inc()
    return INDEX_HTML.replace("__VERSION__", VERSION)


@app.get("/monitoring", response_class=HTMLResponse)
def monitoring_page():
    return MONITORING_HTML


INDEX_HTML = """<!doctype html>
<html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Генератор паролей</title>
<style>
body{font-family:system-ui,sans-serif;max-width:520px;margin:6vh auto;padding:0 16px}
.out{display:flex;gap:8px;margin:16px 0}
#pw{flex:1;font:1.2rem ui-monospace,monospace;padding:10px;border:1px solid #8886;border-radius:8px;word-break:break-all}
button{padding:10px 16px;border-radius:8px;border:0;background:#4a8af4;color:#fff;font-size:1rem;cursor:pointer}
label{display:block;margin:8px 0}
.s{font-weight:600} small,a{color:#888}
</style></head><body>
<h1>🔐 Генератор паролей</h1>
<label>Длина: <b id="lv">16</b>
<input id="len" type="range" min="6" max="64" value="16" style="width:100%"></label>
<label><input id="upper" type="checkbox" checked> Заглавные буквы</label>
<label><input id="digits" type="checkbox" checked> Цифры</label>
<label><input id="symbols" type="checkbox" checked> Символы</label>
<div class="out"><div id="pw">…</div><button id="copy" title="Копировать">📋</button></div>
<p>Надёжность: <span class="s" id="st">—</span> <small id="en"></small></p>
<button id="gen">Сгенерировать</button>
<p><small>Пароль создаётся на сервере и нигде не сохраняется · версия __VERSION__ ·
<a href="/monitoring">мониторинг</a> · <a href="/health">health</a></small></p>
<script>
const $ = id => document.getElementById(id);
$('len').oninput = () => $('lv').textContent = $('len').value;
async function gen(){
  const q = new URLSearchParams({length:$('len').value, upper:$('upper').checked,
    digits:$('digits').checked, symbols:$('symbols').checked});
  try{
    const d = await (await fetch('/api/password?'+q)).json();
    $('pw').textContent = d.password; $('st').textContent = d.strength;
    $('en').textContent = '(' + d.entropy_bits + ' бит)';
  }catch(e){ $('pw').textContent = 'Ошибка соединения'; }
}
$('gen').onclick = gen;
$('copy').onclick = () => navigator.clipboard && navigator.clipboard.writeText($('pw').textContent);
gen();
</script></body></html>"""


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
 <div class="card">Посещений за час<b id="vhour">…</b></div>
 <div class="card">Паролей за час<b id="phour">…</b></div>
 <div class="card">Посещений всего<b id="vtotal">…</b></div>
 <div class="card">Паролей всего<b id="ptotal">…</b></div>
</div>
<h3>Паролей по часам (последние 24 ч)</h3>
<div class="bars" id="pbars"></div>
<h3>Посещений по часам (последние 24 ч)</h3>
<div class="bars" id="vbars"></div>
<p><small>Обновляется каждые 5 секунд. Счётчики хранятся в памяти и обнуляются при перезапуске.</small></p>
<script>
const $ = id => document.getElementById(id);
function bars(el, arr){
  const max = Math.max(1, ...arr);
  $(el).innerHTML = arr.map(v => `<div title="${v}" style="height:${v/max*100}%"></div>`).join('');
}
async function tick(){
  try{
    const d = await (await fetch('/api/monitoring')).json();
    $('health').textContent = d.health; $('health').className = 'up';
    $('uptime').textContent = d.uptime_seconds + ' с';
    $('cpu').textContent = d.resources.process_cpu_percent + ' %';
    $('mem').textContent = d.resources.process_memory_mb + ' МБ';
    $('vhour').textContent = d.visits.last_hour; $('vtotal').textContent = d.visits.total;
    $('phour').textContent = d.passwords.last_hour; $('ptotal').textContent = d.passwords.total;
    bars('vbars', d.visits.by_hour_last_24h); bars('pbars', d.passwords.by_hour_last_24h);
  }catch(e){ $('health').textContent = 'DOWN'; $('health').className = 'down'; }
}
tick(); setInterval(tick, 5000);
</script></body></html>"""
