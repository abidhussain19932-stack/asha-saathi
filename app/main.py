"""FastAPI app: web dashboard, web chat, JSON API and Telegram webhook."""
from __future__ import annotations

import os
import secrets
from datetime import date
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from . import __version__, schedules, telegram, visits
from .agent import Agent
from .db import DB
from .seed import DEMO_TG, seed

app = FastAPI(title="ASHA Saathi", version=__version__)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
db = DB()
agent = Agent(db)
WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET") or secrets.token_hex(16)
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")
BOT_USERNAME = os.environ.get("TELEGRAM_BOT_USERNAME", "")


@app.on_event("startup")
def _startup():
    seed(db)
    if telegram.enabled() and PUBLIC_URL:
        try:
            telegram.set_webhook(f"{PUBLIC_URL}/telegram/webhook", WEBHOOK_SECRET)
        except Exception:
            pass


@app.get("/healthz")
def healthz():
    return {"ok": True, "version": __version__}


@app.get("/", response_class=HTMLResponse)
def dashboard(request: Request):
    today = date.today()
    demo = db.worker(DEMO_TG, is_demo=1)
    items = visits.daily_visits(db, demo["id"], today)
    people = []
    for b in db.beneficiaries(demo["id"]):
        done = db.done_map(b["id"])
        if b["kind"] == "mother":
            lmp = date.fromisoformat(b["lmp"])
            rows = schedules.mother_schedule(lmp, today, done)
            info = f"{schedules.gestational_weeks(lmp, today)} wk · EDD {schedules.edd(lmp):%d-%m-%Y}"
        else:
            dob = date.fromisoformat(b["dob"])
            rows = schedules.child_schedule(dob, today, done)
            info = f"{(today - dob).days} days old"
        nxt = schedules.next_actions(rows)
        up = schedules.next_upcoming(rows)
        people.append({"b": b, "info": info, "next": nxt[:2], "upcoming": up})
    return templates.TemplateResponse(request, "dashboard.html", {
        "today": today, "visits": items, "people": people, "stats": db.stats(),
        "bot": BOT_USERNAME, "version": __version__,
    })


class ChatIn(BaseModel):
    text: str
    session: str | None = None


@app.post("/api/chat")
def api_chat(body: ChatIn):
    if not body.text.strip():
        raise HTTPException(400, "empty")
    sess = (body.session or "anon")[:64]
    worker = db.worker(f"web:{sess}", "web tester")
    reply = agent.handle(worker, body.text[:600], channel="web")
    return {"reply": reply}


@app.get("/api/stats")
def api_stats():
    return db.stats()


@app.get("/api/schedule")
def api_schedule(kind: str, d: str):
    """Pure schedule lookup: kind=mother&d=<LMP> or kind=child&d=<DOB> (YYYY-MM-DD)."""
    base = date.fromisoformat(d)
    rows = schedules.mother_schedule(base, date.today()) if kind == "mother" else schedules.child_schedule(base, date.today())
    return [{**r, "start": r["start"].isoformat(), "end": r["end"].isoformat()} for r in rows]


def _process_update(update: dict):
    msg = update.get("message") or {}
    text = msg.get("text")
    chat = msg.get("chat", {})
    if not text or not chat.get("id"):
        return
    frm = msg.get("from", {})
    worker = db.worker(f"tg:{frm.get('id', chat['id'])}", frm.get("first_name", ""))
    try:
        reply = agent.handle(worker, text[:600], channel="telegram")
    except Exception:
        reply = "माफ़ कीजिए, कुछ गड़बड़ हुई। फिर से कोशिश करें। आपात स्थिति में 108 पर कॉल करें।"
    telegram.send(chat["id"], reply)


@app.post("/telegram/webhook")
async def tg_webhook(request: Request, bg: BackgroundTasks,
                     x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    if x_telegram_bot_api_secret_token != WEBHOOK_SECRET:
        raise HTTPException(403, "bad secret")
    bg.add_task(_process_update, await request.json())
    return JSONResponse({"ok": True})
