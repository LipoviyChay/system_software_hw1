"""Telegram-бот - второй тонкий клиент. Работает через long polling,
поэтому HTTPS и домен для него не нужны."""
import os
import time

import requests

TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
# Если Telegram из вашей сети режется - можно указать зеркало/прокси через эту переменную
TG_BASE = os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org")
API_URL = os.getenv("API_URL", "http://app:8000")


def tg(method: str, **params):
    r = requests.post(f"{TG_BASE}/bot{TOKEN}/{method}", json=params, timeout=40)
    return r.json()


def answer(text: str) -> str:
    parts = text.split()
    cmd = parts[0].split("@")[0].lower() if parts else ""
    try:
        if cmd == "/pass":
            length = 16
            if len(parts) > 1 and parts[1].isdigit():
                length = max(6, min(64, int(parts[1])))
            d = requests.get(f"{API_URL}/api/password", params={"length": length}, timeout=5).json()
            return f"{d['password']}\nНадёжность: {d['strength']} ({d['entropy_bits']} бит)"
        if cmd == "/stats":
            s = requests.get(f"{API_URL}/api/stats", timeout=5).json()
            return (f"Паролей сгенерировано: {s['passwords_generated']}\n"
                    f"Посещений: {s['visits']}\n"
                    f"Аптайм: {s['uptime_seconds']} сек\n"
                    f"Версия: {s['version']}")
        if cmd == "/health":
            h = requests.get(f"{API_URL}/health", timeout=5).json()
            return f"Статус: {h['status']} (версия {h['version']})"
    except Exception as e:  # бэкенд недоступен
        return f"Бэкенд недоступен: {e}"
    return "Команды: /pass [длина] - новый пароль, /stats - статистика, /health - проверка работоспособности"


def main():
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN не задан - бот выключен, жду.", flush=True)
        while True:
            time.sleep(3600)
    offset = None
    print("Бот запущен", flush=True)
    while True:
        try:
            data = tg("getUpdates", offset=offset, timeout=30)
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                if "text" in msg:
                    tg("sendMessage", chat_id=msg["chat"]["id"], text=answer(msg["text"]))
        except Exception as e:
            print("ошибка:", e, flush=True)
            time.sleep(5)


if __name__ == "__main__":
    main()
