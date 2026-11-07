from datetime import date
from app.db import DB
from app.agent import Agent, rule_parse, parse_date
from app.seed import seed
from app import visits

TODAY = date(2026, 11, 7)

def mk():
    db = DB()
    return db, Agent(db, today_fn=lambda: TODAY)

def test_parse_date_formats():
    assert parse_date("LMP 01-08-2026") == date(2026, 8, 1)
    assert parse_date("2026-08-01") == date(2026, 8, 1)
    assert parse_date("१/८/२०२६") == date(2026, 8, 1)

def test_rule_parse_register():
    p = rule_parse("नई गर्भवती सीता LMP 01-08-2026 गाँव रामपुर")
    assert p["intent"] == "register_mother" and p["name"] == "सीता" and p["village"] == "रामपुर"
    c = rule_parse("नया बच्चा राजू जन्म 01-10-2026 माँ गीता")
    assert c["intent"] == "register_child" and c["name"] == "राजू" and c["mother"] == "गीता"

def test_end_to_end_flow():
    db, ag = mk()
    w = db.worker("t1", "test")
    r = ag.handle(w, "नई गर्भवती सीता LMP 01-08-2026 गाँव रामपुर", use_llm=False)
    assert "पंजीकृत" in r and "EDD" in r
    assert "दूसरी प्रसव-पूर्व" in ag.handle(w, "सीता की स्थिति", use_llm=False)
    assert "दर्ज" in ag.handle(w, "सीता ANC1 हो गया", use_llm=False)
    tri = ag.handle(w, "सीता को तेज़ सिरदर्द और धुंधला दिख रहा है", use_llm=False)
    assert "108" in tri and "🔴" in tri
    vis = ag.handle(w, "आज की सूची", use_llm=False)
    assert "सीता" in vis and "फ़ॉलो-अप" in vis
    assert db.stats()["triage_red"] >= 1

def test_months_pregnant_and_child():
    db, ag = mk()
    w = db.worker("t2", "test")
    assert "पंजीकृत" in ag.handle(w, "नई गर्भवती कमला LMP 5 महीने", use_llm=False)
    r = ag.handle(w, "नया बच्चा चिंटू जन्म 01-11-2026", use_llm=False)
    assert "पंजीकृत" in r and "HBNC" in r

def test_seed_visit_list_nonempty():
    db, _ = mk()
    wid = seed(db, TODAY)
    items = visits.daily_visits(db, wid, TODAY)
    names = [i["beneficiary"]["name"] for i in items]
    assert any("मुन्नी" in n for n in names)  # newborn on HBNC day 7

def test_unknown_gets_help():
    db, ag = mk()
    w = db.worker("t3", "x")
    assert "मदद" in ag.handle(w, "asdfgh", use_llm=False)
