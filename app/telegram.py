"""Minimal Telegram Bot API client (webhook mode, no extra dependency)."""
from __future__ import annotations

import os

import httpx

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
API = f"https://api.telegram.org/bot{TOKEN}"


def enabled() -> bool:
    return bool(TOKEN)


def send(chat_id: int | str, text: str) -> None:
    if not TOKEN:
        return
    for i in range(0, len(text), 4000):
        httpx.post(f"{API}/sendMessage", json={"chat_id": chat_id, "text": text[i:i + 4000]}, timeout=15)


def set_webhook(url: str, secret: str) -> dict:
    r = httpx.post(f"{API}/setWebhook", json={"url": url, "secret_token": secret,
                                               "allowed_updates": ["message"]}, timeout=15)
    return r.json()
