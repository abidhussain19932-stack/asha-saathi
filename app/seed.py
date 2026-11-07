"""Synthetic demo data (fictional names). Never real patients."""
from __future__ import annotations

from datetime import date, timedelta

from .db import DB

DEMO_TG = "demo-worker"

MOTHERS = [  # name, village, days since LMP, done codes
    ("सीता देवी", "रामपुर", 60, []),
    ("गीता कुमारी", "रामपुर", 150, ["ANC1", "TD1"]),
    ("रीना", "शिवपुर", 200, ["ANC1", "TD1", "TD2", "ANC2"]),
    ("पूजा", "शिवपुर", 255, ["ANC1", "TD1", "TD2", "ANC2", "ANC3"]),
    ("सलमा बानो", "नयागाँव", 100, ["ANC1"]),
]
CHILDREN = [  # name, village, age days, done codes
    ("मुन्नी (गीता की बेटी)", "रामपुर", 7, ["BCG", "OPV0", "HEPB0"]),
    ("राजू", "शिवपुर", 45, ["BCG", "OPV0", "HEPB0"]),
    ("आरिफ़", "नयागाँव", 100, ["BCG", "OPV0", "HEPB0", "W6", "W10"]),
    ("लक्ष्मी", "रामपुर", 280, ["BCG", "OPV0", "HEPB0", "W6", "W10", "W14"]),
]


def seed(db: DB, today: date | None = None) -> int:
    today = today or date.today()
    w = db.worker(DEMO_TG, "डेमो ASHA सुनीता (synthetic)", is_demo=1)
    if db.beneficiaries(w["id"]):
        return w["id"]
    for name, vil, d, done in MOTHERS:
        lmp = today - timedelta(days=d)
        bid = db.insert("beneficiaries", worker_id=w["id"], kind="mother", name=name, village=vil,
                        lmp=lmp.isoformat(), is_synthetic=1)
        for c in done:
            db.insert("events", beneficiary_id=bid, code=c, done_on=today.isoformat())
    for name, vil, d, done in CHILDREN:
        dob = today - timedelta(days=d)
        bid = db.insert("beneficiaries", worker_id=w["id"], kind="child", name=name, village=vil,
                        dob=dob.isoformat(), is_synthetic=1)
        for c in done:
            db.insert("events", beneficiary_id=bid, code=c, done_on=dob.isoformat())
    return w["id"]
