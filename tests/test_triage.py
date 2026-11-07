import pytest
from app.triage import triage

@pytest.mark.parametrize("text", [
    "सीता को खून आ रहा है", "तेज़ सिरदर्द और धुंधला दिख रहा है", "उसे दौरे पड़ रहे हैं",
    "पानी की थैली फट गई", "बच्चे का हिलना बंद हो गया", "heavy bleeding since morning",
    "bp 165/112", "hb 6.5",
])
def test_mother_red(text):
    assert triage(text, "mother").level == "RED"

@pytest.mark.parametrize("text", ["हाथ पैर में सूजन है", "bp 145/92", "हल्का बुखार है", "hb 9"])
def test_mother_yellow(text):
    assert triage(text, "mother").level == "YELLOW"

@pytest.mark.parametrize("text", ["बच्चा दूध नहीं पी रहा", "बच्चा बहुत सुस्त है", "पसली चल रही है",
                                  "breathing 65 breaths per minute", "शरीर ठंडा है"])
def test_newborn_red(text):
    assert triage(text, "child", age_days=10).level == "RED"

def test_newborn_jaundice_yellow():
    assert triage("आँखें पीली हैं, पीलिया लगता है", "child", 5).level == "YELLOW"

def test_fast_breathing_cutoff_by_age():
    assert triage("55 breaths", "child", age_days=30).level == "GREEN"  # <60 for <2 months is not fast
    assert triage("55 breaths", "child", age_days=200).level == "RED"   # >=50 for 2-12 months

@pytest.mark.parametrize("text", ["सब ठीक है", "बुखार नहीं है", "no bleeding", "खून की कमी की जाँच हुई"])
def test_green_and_negation(text):
    assert triage(text, "mother").level == "GREEN"

def test_always_disclaims():
    t = triage("तेज़ सिरदर्द", "mother").to_text_hi()
    assert "निदान नहीं" in t and "108" in t
