"""Daily home-visit list: who should the ASHA visit today, and why.

Priority (highest first):
  1. A RED/YELLOW triage result in the last 7 days (follow-up)
  2. Newborns on an HBNC visit day (3, 7, 14, 21, 28, 42 - MoHFW HBNC guidelines)
  3. Overdue ANC check-ups / vaccines
  4. Pregnant women at 36+ weeks (birth preparedness)
  5. Items whose window closes within 7 days
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import schedules
from .db import DB

HBNC_DAYS = (3, 7, 14, 21, 28, 42)


def daily_visits(db: DB, worker_id: int, today: date) -> list[dict]:
    out = []
    since = (datetime.combine(today - timedelta(days=7), datetime.min.time())).isoformat()
    recent = db.q("SELECT beneficiary_id, level FROM triage_log WHERE worker_id=? AND created_at>=? "
                  "AND level IN ('RED','YELLOW')", (worker_id, since))
    flagged = {}
    for r in recent:
        if r["beneficiary_id"]:
            flagged[r["beneficiary_id"]] = "RED" if r["level"] == "RED" or flagged.get(r["beneficiary_id"]) == "RED" else "YELLOW"
    for b in db.beneficiaries(worker_id):
        done = db.done_map(b["id"])
        reasons, score = [], 0
        if b["id"] in flagged:
            lvl = flagged[b["id"]]
            reasons.append("🔴 खतरे के संकेत - फ़ॉलो-अप" if lvl == "RED" else "🟡 रेफ़रल फ़ॉलो-अप")
            score += 100 if lvl == "RED" else 60
        if b["kind"] == "mother":
            lmp = date.fromisoformat(b["lmp"])
            if schedules.edd(lmp) + timedelta(days=42) < today:
                continue  # postpartum period over; mother no longer on the ANC list
            rows = schedules.mother_schedule(lmp, today, done)
            wk = schedules.gestational_weeks(lmp, today)
            if 36 <= wk <= 42:
                reasons.append(f"🤰 {wk} सप्ताह - प्रसव की तैयारी, संस्थागत प्रसव योजना")
                score += 30
        else:
            dob = date.fromisoformat(b["dob"])
            age = (today - dob).days
            rows = schedules.child_schedule(dob, today, done)
            if age in HBNC_DAYS:
                reasons.append(f"👶 HBNC गृह भ्रमण - दिन {age}")
                score += 50
        for r in rows:
            if r["status"] == "overdue" and (today - r["end"]).days <= 365:
                reasons.append(f"⏰ देर: {r['name_hi']}")
                score += 20
            elif r["status"] == "due" and (r["end"] - today).days <= 7:
                reasons.append(f"📌 जल्दी करें: {r['name_hi']} (अंतिम {r['end'].strftime('%d-%m')})")
                score += 10
        if reasons:
            out.append({"beneficiary": b, "reasons": reasons, "score": score})
    out.sort(key=lambda x: -x["score"])
    return out


def format_hi(items: list[dict], today: date) -> str:
    if not items:
        return f"📅 {today.strftime('%d-%m-%Y')}: आज कोई ज़रूरी गृह भ्रमण नहीं। 'सूची' से सभी लाभार्थी देखें।"
    lines = [f"📅 आज की गृह भ्रमण सूची ({today.strftime('%d-%m-%Y')}) - {len(items)} घर:"]
    for i, it in enumerate(items[:15], 1):
        b = it["beneficiary"]
        tag = "🤰" if b["kind"] == "mother" else "👶"
        lines.append(f"\n{i}. {tag} {b['name']} ({b.get('village') or '-'})")
        lines.extend(f"   {r}" for r in it["reasons"][:4])
    return "\n".join(lines)
