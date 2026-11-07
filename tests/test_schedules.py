from datetime import date, timedelta
from app import schedules as s

LMP = date(2026, 6, 1)

def test_edd_is_280_days():
    assert s.edd(LMP) == date(2027, 3, 8)

def test_anc_windows_match_mohfw():
    rows = {r["code"]: r for r in s.mother_schedule(LMP, LMP)}
    assert rows["ANC1"]["end"] == LMP + timedelta(weeks=12)
    assert rows["ANC2"]["start"] == LMP + timedelta(weeks=14) and rows["ANC2"]["end"] == LMP + timedelta(weeks=26)
    assert rows["ANC3"]["start"] == LMP + timedelta(weeks=28) and rows["ANC3"]["end"] == LMP + timedelta(weeks=34)
    assert rows["ANC4"]["start"] == LMP + timedelta(weeks=36)

def test_td2_four_weeks_after_td1():
    td1 = LMP + timedelta(weeks=10)
    rows = {r["code"]: r for r in s.mother_schedule(LMP, td1, {"TD1": td1})}
    assert rows["TD2"]["start"] == td1 + timedelta(days=28)

def test_status_transitions():
    today = LMP + timedelta(weeks=20)
    rows = {r["code"]: r for r in s.mother_schedule(LMP, today, {"ANC1": LMP})}
    assert rows["ANC1"]["status"] == "done"
    assert rows["ANC2"]["status"] == "due"
    assert rows["ANC3"]["status"] == "upcoming"
    later = {r["code"]: r for r in s.mother_schedule(LMP, LMP + timedelta(weeks=27))}
    assert later["ANC2"]["status"] == "overdue"

def test_child_uip_offsets():
    dob = date(2026, 1, 1)
    rows = {r["code"]: r for r in s.child_schedule(dob, dob)}
    assert rows["W6"]["start"] == dob + timedelta(weeks=6)
    assert rows["W10"]["start"] == dob + timedelta(weeks=10)
    assert rows["W14"]["start"] == dob + timedelta(weeks=14)
    assert rows["BCG"]["status"] == "due" and rows["HEPB0"]["end"] == dob + timedelta(days=1)
    assert "MR-1" in rows["M9"]["name_en"] and "MR-2" in rows["M16"]["name_en"]

def test_next_actions_overdue_first():
    dob = date(2026, 1, 1)
    rows = s.child_schedule(dob, dob + timedelta(days=50), {"BCG": dob, "OPV0": dob, "HEPB0": dob})
    acts = s.next_actions(rows)
    assert acts[0]["code"] == "W6"
