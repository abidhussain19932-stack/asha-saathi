"""The ASHA Saathi agent.

Design: the LLM (Groq, openai/gpt-oss-120b) is used only to UNDERSTAND a free
Hindi/Hinglish message and turn it into a small JSON tool call. Every medical
decision is made by deterministic tools:

    register_mother / register_child -> db
    due_list                         -> schedules.py (MoHFW ANC + UIP NIS)
    record_done                      -> db
    triage                           -> triage.py (fixed danger-sign rules)
    visit_list                       -> visits.py

If the LLM is unavailable (no key, rate-limited, offline) a rule-based parser
handles slash commands and common Hindi phrasings, so the bot keeps working.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta

import httpx

from . import schedules, triage as triage_mod, visits
from .db import DB

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")

LAST_LLM_ERROR = ""

INTENTS = ("help", "register_mother", "register_child", "visit_list", "due_list",
           "record_done", "triage", "list", "unknown")

SYSTEM_PROMPT = (
    "You convert an ASHA health worker's message (Hindi, Hinglish or English) into JSON. "
    "Never give medical advice. Output ONLY a JSON object with keys: "
    "intent (one of help, register_mother, register_child, visit_list, due_list, record_done, triage, list, unknown), "
    "name (person's name or null), date (YYYY-MM-DD or null: LMP for a pregnant woman, birth date for a child), "
    "months (number or null: months pregnant, or child's age in months, if said instead of a date), "
    "village (or null), mother (mother's name for a child, or null), "
    "code (one of ANC1 ANC2 ANC3 ANC4 TD1 TD2 BCG OPV0 HEPB0 W6 W10 W14 M9 M16 Y5, or null), "
    "symptoms (the symptom words copied as written, or null). "
    "list means list ALL beneficiaries (no name); due_list means one named person's status or schedule. Use triage whenever any symptom or illness is mentioned."
)

HELP_HI = (
    "🙏 नमस्ते! मैं ASHA Saathi हूँ - आपकी डिजिटल सहेली।\n\n"
    "आप ऐसे लिख सकती हैं:\n"
    "• नई गर्भवती सीता LMP 01-08-2026 गाँव रामपुर\n"
    "• नया बच्चा राजू जन्म 01-10-2026 माँ गीता\n"
    "• आज की सूची  (आज किसके घर जाना है)\n"
    "• सीता की स्थिति  (कौन सी जाँच/टीका बाकी)\n"
    "• सीता ANC2 हो गया\n"
    "• सीता को तेज़ सिरदर्द और धुंधला दिख रहा है  (खतरे के संकेत जाँच)\n"
    "• सूची  (आपके सभी लाभार्थी)\n\n"
    "Commands: /mother /child /visits /due /done /check /list\n"
    "⚠️ केवल डेमो/काल्पनिक डेटा डालें। मैं निदान नहीं करता - आपात स्थिति में 108 पर कॉल करें।"
)

# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")


def parse_date(text: str) -> date | None:
    t = text.translate(_DEV_DIGITS)
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = map(int, m.groups())
    else:
        m = re.search(r"(\d{1,2})[-/.](\d{1,2})[-/.](\d{2,4})", t)
        if not m:
            return None
        d, mo, y = map(int, m.groups())
        if y < 100:
            y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def parse_months(text: str) -> float | None:
    t = text.translate(_DEV_DIGITS).lower()
    m = re.search(r"(\d{1,2}(?:\.\d)?)\s*(?:महीने|महीना|माह|month|mahine|mahina)", t)
    return float(m.group(1)) if m else None


CODE_ALIASES = {
    "anc1": "ANC1", "anc2": "ANC2", "anc3": "ANC3", "anc4": "ANC4", "anc 1": "ANC1", "anc 2": "ANC2",
    "anc 3": "ANC3", "anc 4": "ANC4", "td1": "TD1", "td2": "TD2", "td-1": "TD1", "td-2": "TD2",
    "bcg": "BCG", "बीसीजी": "BCG", "opv0": "OPV0", "hepb": "HEPB0", "6 सप्ताह": "W6", "6 week": "W6",
    "10 सप्ताह": "W10", "10 week": "W10", "14 सप्ताह": "W14", "14 week": "W14", "w6": "W6", "w10": "W10",
    "w14": "W14", "m9": "M9", "9 माह": "M9", "9 month": "M9", "mr1": "M9", "mr-1": "M9", "m16": "M16",
    "mr2": "M16", "mr-2": "M16", "y5": "Y5",
}


def parse_code(text: str) -> str | None:
    t = text.lower()
    for k in sorted(CODE_ALIASES, key=len, reverse=True):
        if k in t:
            return CODE_ALIASES[k]
    return None


_STOP = {"नई", "नया", "गर्भवती", "बच्चा", "बच्ची", "lmp", "जन्म", "गाँव", "गांव", "माँ", "मां", "को", "का", "की",
         "स्थिति", "हो", "गया", "गई", "register", "mother", "child", "village", "new", "pregnant", "baby",
         "/mother", "/child", "/due", "/done", "/check", "dob", "status", "है", "और", "में", "रहा", "रही",
         "meri", "mera", "meri", "nayi", "naya", "nai", "mareez", "marij", "hai", "ki", "ka", "ko", "aur", "gaon",
         "mahine", "mahina", "months", "month", "महीने", "महीना", "माह", "मेरी", "मेरा", "मरीज़", "मरीज", "नाम",
         "naam", "name", "is", "a", "the", "my", "she", "wo", "woh", "वो", "वह"}


def _first_name(text: str) -> str | None:
    for w in re.split(r"[\s,।]+", text):
        w2 = w.strip().strip(":")
        if not w2 or w2.lower() in _STOP or any(ch.isdigit() for ch in w2.translate(_DEV_DIGITS)):
            continue
        if parse_code(w2):
            continue
        return w2
    return None


def _after(text: str, keys: tuple[str, ...]) -> str | None:
    for k in keys:
        m = re.search(re.escape(k) + r"\s*[:\-]?\s*([^\s,।]+)", text, re.IGNORECASE)
        if m:
            return m.group(1)
    return None


def rule_parse(text: str) -> dict:
    """Deterministic fallback parser for commands and common phrasings."""
    t = text.strip()
    low = t.lower()
    out = {"intent": "unknown", "name": None, "date": None, "months": None, "village": None,
           "mother": None, "code": None, "symptoms": None}
    d = parse_date(t)
    out["date"] = d.isoformat() if d else None
    out["months"] = parse_months(t)
    out["village"] = _after(t, ("गाँव", "गांव", "village", "gaon"))
    out["mother"] = _after(t, ("माँ", "मां", "mother", "maa"))

    def strip_cmd(s: str) -> str:
        return re.sub(r"^/\w+\s*", "", s)

    if low in ("/start", "start", "help", "/help", "मदद", "हेल्प", "नमस्ते", "hi", "hello"):
        out["intent"] = "help"
    elif low.startswith("/mother") or "गर्भवती" in t or "pregnant" in low or "lmp" in low:
        out["intent"] = "register_mother"
        out["name"] = _first_name(strip_cmd(t))
    elif low.startswith("/child") or "नया बच्चा" in t or "नई बच्ची" in t or "new baby" in low or "जन्म" in t:
        out["intent"] = "register_child"
        rest = strip_cmd(t)
        if out["mother"]:
            rest = re.sub(r"(माँ|मां|mother|maa)\s*[:\-]?\s*\S+", "", rest, flags=re.IGNORECASE)
        out["name"] = _first_name(rest)
    elif low.startswith("/visits") or "आज" in t or "visit" in low or "aaj" in low:
        out["intent"] = "visit_list"
    elif low.startswith("/list") or low in ("सूची", "list", "सब"):
        out["intent"] = "list"
    elif low.startswith("/done") or "हो गया" in t or "हो गई" in t or "लग गया" in t or "done" in low:
        out["intent"] = "record_done"
        out["name"] = _first_name(strip_cmd(t))
        out["code"] = parse_code(t)
    elif low.startswith("/due") or "स्थिति" in t or "status" in low or "बाकी" in t:
        out["intent"] = "due_list"
        out["name"] = _first_name(strip_cmd(t))
    elif low.startswith("/check") or triage_mod.triage(t, "mother").level != "GREEN" \
            or triage_mod.triage(t, "child").level != "GREEN":
        out["intent"] = "triage"
        out["name"] = _first_name(strip_cmd(t))
        out["symptoms"] = strip_cmd(t)
    return out


def llm_parse(text: str, timeout: float = 12.0) -> dict | None:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        return None
    try:
        r = httpx.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {key}"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT},
                             {"role": "user", "content": text[:500]}],
                "temperature": 0,
                "max_tokens": 300,
                "response_format": {"type": "json_object"},
            },
            timeout=timeout,
        )
        r.raise_for_status()
        data = json.loads(r.json()["choices"][0]["message"]["content"])
        if data.get("intent") not in INTENTS:
            return None
        return data
    except Exception as e:  # never log the key; record the failure type for /healthz
        global LAST_LLM_ERROR
        LAST_LLM_ERROR = f"{type(e).__name__}: {str(e)[:160]}"
        print("LLM parse failed:", LAST_LLM_ERROR, flush=True)
        return None


# --------------------------------------------------------------------------
# Agent
# --------------------------------------------------------------------------
class Agent:
    def __init__(self, db: DB, today_fn=date.today):
        self.db = db
        self.today_fn = today_fn

    def handle(self, worker: dict, text: str, channel: str = "telegram", use_llm: bool = True) -> str:
        parsed = rule_parse(text)
        llm_used = False
        # Slash commands and confident rule parses skip the LLM (cheaper, faster).
        if use_llm and not text.startswith("/") and parsed["intent"] in ("unknown", "triage", "register_mother",
                                                                          "register_child", "record_done", "due_list"):
            got = llm_parse(text)
            if got:
                llm_used = True
                rule_intent = parsed["intent"]
                for k, v in got.items():
                    if v not in (None, "", "null"):
                        parsed[k] = v
                # The rule parser's intent wins when it is confident; the LLM fills the slots
                # (name, date, months, village, symptoms) and decides only when rules are unsure.
                if rule_intent != "unknown":
                    parsed["intent"] = rule_intent
                # Safety: if rules see a danger sign, triage always wins.
                if rule_intent == "triage":
                    parsed["symptoms"] = parsed.get("symptoms") or text
        intent = parsed.get("intent", "unknown")
        self.db.log(worker["id"], channel, intent, llm_used)
        fn = getattr(self, f"do_{intent}", None)
        if not fn:
            return "माफ़ कीजिए, समझ नहीं पाया। 'मदद' लिखें।\n\n" + HELP_HI
        return fn(worker, parsed, text)

    # ---- tools ----------------------------------------------------------
    def do_help(self, worker, p, text):
        return HELP_HI

    def do_unknown(self, worker, p, text):
        return "माफ़ कीजिए, समझ नहीं पाया। 'मदद' लिखें।\n\n" + HELP_HI

    def _date_from(self, p: dict) -> date | None:
        if p.get("date"):
            try:
                return date.fromisoformat(str(p["date"]))
            except ValueError:
                pass
        if p.get("months"):
            return self.today_fn() - timedelta(days=round(float(p["months"]) * 30.44))
        return None

    def do_register_mother(self, worker, p, text):
        name, lmp = p.get("name"), self._date_from(p)
        if not name or not lmp:
            return "कृपया नाम और LMP (आखिरी माहवारी की तारीख) लिखें, जैसे:\nनई गर्भवती सीता LMP 01-08-2026 गाँव रामपुर"
        today = self.today_fn()
        if lmp > today or (today - lmp).days > 300:
            return "LMP की तारीख सही नहीं लग रही (भविष्य की या 10 महीने से पुरानी)। कृपया जाँचें।"
        bid = self.db.insert("beneficiaries", worker_id=worker["id"], kind="mother", name=name,
                             village=p.get("village"), lmp=lmp.isoformat(), is_synthetic=1)
        rows = schedules.mother_schedule(lmp, today)
        nxt = schedules.next_actions(rows)[:2] or [schedules.next_upcoming(rows)]
        lines = [f"✅ {name} पंजीकृत (ID {bid}).",
                 f"गर्भ: {schedules.gestational_weeks(lmp, today)} सप्ताह | संभावित प्रसव तिथि (EDD): {_d(schedules.edd(lmp))}"]
        for r in [x for x in nxt if x]:
            lines.append(f"• {r['name_hi']}: {_d(r['start'])} - {_d(r['end'])} ({schedules.STATUS_HI[r['status']]})")
        lines.append("📅 PMSMA: हर महीने की 9 तारीख को PHC पर मुफ़्त जाँच।")
        return "\n".join(lines)

    def do_register_child(self, worker, p, text):
        name, dob = p.get("name"), self._date_from(p)
        if not name or not dob:
            return "कृपया बच्चे का नाम और जन्म तिथि लिखें, जैसे:\nनया बच्चा राजू जन्म 01-10-2026 माँ गीता"
        today = self.today_fn()
        if dob > today or (today - dob).days > 7 * 365:
            return "जन्म तिथि सही नहीं लग रही। कृपया जाँचें।"
        mother_id = None
        if p.get("mother"):
            m = self.db.find(worker["id"], p["mother"])
            mother_id = m[0]["id"] if m else None
        bid = self.db.insert("beneficiaries", worker_id=worker["id"], kind="child", name=name,
                             village=p.get("village"), dob=dob.isoformat(), mother_id=mother_id, is_synthetic=1)
        rows = schedules.child_schedule(dob, today)
        lines = [f"✅ {name} पंजीकृत (ID {bid}). उम्र: {(today - dob).days} दिन"]
        for r in schedules.next_actions(rows)[:3]:
            lines.append(f"• {r['name_hi']} - {schedules.STATUS_HI[r['status']]} (अंतिम {_d(r['end'])})")
        up = schedules.next_upcoming(rows)
        if up:
            lines.append(f"अगला: {up['name_hi']} - {_d(up['start'])} से")
        if (today - dob).days <= 42:
            lines.append("🏠 HBNC: नवजात के घर 3, 7, 14, 21, 28 और 42वें दिन जाएँ (घर पर जन्म हो तो पहले दिन भी)।")
        return "\n".join(lines)

    def _pick(self, worker, name: str | None) -> tuple[dict | None, str | None]:
        if not name:
            return None, "किसकी? कृपया नाम लिखें।"
        found = self.db.find(worker["id"], name)
        if not found:
            return None, f"'{name}' नाम का कोई लाभार्थी नहीं मिला। 'सूची' लिखकर देखें।"
        return found[0], None

    def _rows(self, b: dict) -> list[dict]:
        done = self.db.done_map(b["id"])
        today = self.today_fn()
        if b["kind"] == "mother":
            return schedules.mother_schedule(date.fromisoformat(b["lmp"]), today, done)
        return schedules.child_schedule(date.fromisoformat(b["dob"]), today, done)

    def do_due_list(self, worker, p, text):
        b, err = self._pick(worker, p.get("name"))
        if err:
            return err
        lines = [f"📋 {b['name']} ({'गर्भवती' if b['kind'] == 'mother' else 'बच्चा'})"]
        if b["kind"] == "mother":
            lmp = date.fromisoformat(b["lmp"])
            lines.append(f"गर्भ {schedules.gestational_weeks(lmp, self.today_fn())} सप्ताह | EDD {_d(schedules.edd(lmp))}")
        icon = {"done": "✅", "overdue": "🔴", "due": "🟠", "upcoming": "⚪"}
        for r in self._rows(b):
            lines.append(f"{icon[r['status']]} {r['name_hi']} ({_d(r['start'])} - {_d(r['end'])})")
        lines.append("✅ हो गया  🔴 देर  🟠 अभी देय  ⚪ आगे")
        return "\n".join(lines)

    def do_record_done(self, worker, p, text):
        b, err = self._pick(worker, p.get("name"))
        if err:
            return err
        code = p.get("code") or parse_code(text)
        valid = {r["code"]: r for r in self._rows(b)}
        if code not in valid:
            return "कौन सी जाँच/टीका? जैसे: सीता ANC2 हो गया  या  राजू 6 सप्ताह हो गया"
        d = parse_date(text) or self.today_fn()
        self.db.insert("events", beneficiary_id=b["id"], code=code, done_on=d.isoformat())
        return f"✅ दर्ज: {b['name']} - {valid[code]['name_hi']} ({_d(d)})"

    def do_triage(self, worker, p, text):
        b = None
        if p.get("name"):
            found = self.db.find(worker["id"], p["name"])
            b = found[0] if found else None
        kind, age_days = "mother", None
        if b and b["kind"] == "child":
            kind, age_days = "child", (self.today_fn() - date.fromisoformat(b["dob"])).days
        elif not b and re.search(r"बच्च|शिशु|नवजात|baby|child|infant", text, re.IGNORECASE):
            kind = "child"
        res = triage_mod.triage(text, kind, age_days)
        self.db.insert("triage_log", worker_id=worker["id"], beneficiary_id=b["id"] if b else None,
                       level=res.level, signs=",".join(s.code for s in res.signs + []) or ",".join(res.vitals_flags))
        head = f"🩺 {b['name']}: " if b else "🩺 "
        return head + res.to_text_hi()

    def do_list(self, worker, p, text):
        rows = self.db.beneficiaries(worker["id"])
        if not rows:
            return "अभी कोई लाभार्थी नहीं। 'मदद' लिखकर पंजीकरण का तरीका देखें।"
        lines = ["👥 आपके लाभार्थी:"]
        for b in rows:
            tag = "🤰" if b["kind"] == "mother" else "👶"
            lines.append(f"{tag} {b['name']} ({b.get('village') or '-'})")
        return "\n".join(lines)

    def do_visit_list(self, worker, p, text):
        items = visits.daily_visits(self.db, worker["id"], self.today_fn())
        return visits.format_hi(items, self.today_fn())


def _d(d: date) -> str:
    return d.strftime("%d-%m-%Y")
