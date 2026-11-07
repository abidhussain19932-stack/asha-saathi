"""National schedules used by ASHA Saathi.

Sources (see docs/SOURCES.md):
- ANC: MoHFW "Guidelines for Antenatal Care and Skilled Attendance at Birth by
  ANMs/LHVs/SNs" (2010): minimum 4 ANC visits - 1st within 12 weeks,
  2nd 14-26 weeks, 3rd 28-34 weeks, 4th 36 weeks to term.
- Td for pregnant women and the child schedule: MoHFW National Immunization
  Schedule (NIS) under the Universal Immunization Programme, as listed on
  U-WIN (https://uwin.mohfw.gov.in/faq) and NHM
  (https://nhm.gov.in/New_Updates_2018/NHM_Components/Immunization/report/National_%20Immunization_Schedule.pdf).

The schedule is data, not model output: the LLM never computes a due date.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

EDD_DAYS = 280  # Naegele's rule: LMP + 280 days


@dataclass(frozen=True)
class Item:
    code: str
    name_en: str
    name_hi: str
    start_days: int       # window opens (days after LMP or DOB)
    end_days: int         # window closes / max age
    note: str = ""


# ---- Antenatal care (offsets are days after LMP) --------------------------
ANC_ITEMS: list[Item] = [
    Item("ANC1", "1st ANC check-up (registration)", "पहली प्रसव-पूर्व जाँच (पंजीकरण)", 0, 12 * 7),
    Item("TD1", "Td-1 injection", "टीडी-1 टीका", 0, 20 * 7, "Early in pregnancy"),
    Item("ANC2", "2nd ANC check-up", "दूसरी प्रसव-पूर्व जाँच", 14 * 7, 26 * 7),
    Item("ANC3", "3rd ANC check-up", "तीसरी प्रसव-पूर्व जाँच", 28 * 7, 34 * 7),
    Item("ANC4", "4th ANC check-up", "चौथी प्रसव-पूर्व जाँच", 36 * 7, 40 * 7),
]
# Td-2 is 4 weeks after Td-1; handled dynamically in mother_schedule().

W = 7
M = 30  # month approximation used for windows quoted in months
# ---- Child immunisation (offsets are days after DOB) ----------------------
CHILD_ITEMS: list[Item] = [
    Item("BCG", "BCG", "बीसीजी", 0, 365),
    Item("OPV0", "OPV-0", "ओपीवी-0 (पोलियो ड्रॉप)", 0, 15),
    Item("HEPB0", "Hepatitis B birth dose", "हेपेटाइटिस बी जन्म खुराक", 0, 1),
    Item("W6", "6 weeks: OPV-1, Penta-1, Rota-1, fIPV-1, PCV-1", "6 सप्ताह: ओपीवी-1, पेंटा-1, रोटा-1, एफआईपीवी-1, पीसीवी-1", 6 * W, 365),
    Item("W10", "10 weeks: OPV-2, Penta-2, Rota-2", "10 सप्ताह: ओपीवी-2, पेंटा-2, रोटा-2", 10 * W, 365),
    Item("W14", "14 weeks: OPV-3, Penta-3, Rota-3, fIPV-2, PCV-2", "14 सप्ताह: ओपीवी-3, पेंटा-3, रोटा-3, एफआईपीवी-2, पीसीवी-2", 14 * W, 365),
    Item("M9", "9-12 months: MR-1, JE-1*, PCV-Booster, fIPV-3, Vitamin A-1", "9-12 माह: एमआर-1, जेई-1*, पीसीवी बूस्टर, एफआईपीवी-3, विटामिन ए-1", 9 * M, 12 * M, "*JE in endemic districts"),
    Item("M16", "16-24 months: MR-2, JE-2*, DPT-B1, OPV-B, Vitamin A-2", "16-24 माह: एमआर-2, जेई-2*, डीपीटी बूस्टर-1, ओपीवी बूस्टर, विटामिन ए-2", 16 * M, 24 * M, "*JE in endemic districts"),
    Item("Y5", "5-6 years: DPT-Booster-2", "5-6 वर्ष: डीपीटी बूस्टर-2", 5 * 365, 6 * 365 + 364),
]

STATUS_HI = {"done": "हो गया", "overdue": "देर - तुरंत करवाएँ", "due": "अभी देय", "upcoming": "आगे"}


def edd(lmp: date) -> date:
    return lmp + timedelta(days=EDD_DAYS)


def gestational_weeks(lmp: date, today: date) -> int:
    return max(0, (today - lmp).days // 7)


def _status(start: date, end: date, today: date, done: bool) -> str:
    if done:
        return "done"
    if today > end:
        return "overdue"
    if today >= start:
        return "due"
    return "upcoming"


def mother_schedule(lmp: date, today: date, done: dict[str, date] | None = None) -> list[dict]:
    done = done or {}
    out = []
    for it in ANC_ITEMS:
        s, e = lmp + timedelta(days=it.start_days), lmp + timedelta(days=it.end_days)
        out.append(_row(it, s, e, today, it.code in done))
    # Td-2: 4 weeks after Td-1 (if Td-1 recorded), otherwise 4 weeks after the Td-1 window opens
    td1 = done.get("TD1", lmp)
    s = td1 + timedelta(days=28)
    e = max(s, edd(lmp) - timedelta(days=28))
    td2 = Item("TD2", "Td-2 injection (4 weeks after Td-1)", "टीडी-2 टीका (टीडी-1 के 4 सप्ताह बाद)", 0, 0)
    out.append(_row(td2, s, e, today, "TD2" in done))
    out.sort(key=lambda r: r["start"])
    return out


def child_schedule(dob: date, today: date, done: dict[str, date] | None = None) -> list[dict]:
    done = done or {}
    return [_row(it, dob + timedelta(days=it.start_days), dob + timedelta(days=it.end_days), today, it.code in done)
            for it in CHILD_ITEMS]


def _row(it: Item, start: date, end: date, today: date, is_done: bool) -> dict:
    return {
        "code": it.code, "name_en": it.name_en, "name_hi": it.name_hi,
        "start": start, "end": end, "note": it.note,
        "status": _status(start, end, today, is_done),
    }


def next_actions(rows: list[dict]) -> list[dict]:
    """Overdue first, then due now."""
    order = {"overdue": 0, "due": 1}
    return sorted([r for r in rows if r["status"] in order], key=lambda r: (order[r["status"]], r["start"]))


def next_upcoming(rows: list[dict]) -> dict | None:
    up = [r for r in rows if r["status"] == "upcoming"]
    return min(up, key=lambda r: r["start"]) if up else None
