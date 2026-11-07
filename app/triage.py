"""Fixed, rule-based danger-sign triage.

ASHA Saathi NEVER diagnoses. It matches the danger signs ASHAs are trained to
recognise (MoHFW ASHA modules 6 & 7, Home Based Newborn Care (HBNC) and the
MoHFW ANC guidelines - see docs/SOURCES.md) and tells the ASHA where to refer:

  RED    -> emergency: call 108 / take to the nearest FRU/CHC now
  YELLOW -> refer to the PHC / ANM within 24 hours
  GREEN  -> no danger sign matched; continue routine care

The LLM is not involved in this decision. Rules are keyword + vitals based so
they are auditable and testable (see tests/test_triage.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

DISCLAIMER_HI = "⚠️ यह निदान नहीं है। ASHA Saathi केवल खतरे के संकेत पहचानकर रेफ़र करने में मदद करता है।"


@dataclass(frozen=True)
class Sign:
    code: str
    level: str  # RED / YELLOW
    label_hi: str
    label_en: str
    keywords: tuple[str, ...]
    applies_to: tuple[str, ...] = ("mother", "child")
    exclude: tuple[str, ...] = ()  # phrases that mean something else


# Keywords: Devanagari, romanised Hindi (Hinglish) and English. Lower-cased match.
SIGNS: list[Sign] = [
    # ---- Pregnancy / postpartum ---------------------------------------
    Sign("BLEEDING", "RED", "योनि से रक्तस्राव", "Vaginal bleeding",
         ("खून", "रक्तस्राव", "bleeding", "khoon", "khun", "blood"), ("mother",),
         ("खून की कमी", "khoon ki kami", "khun ki kami", "blood test", "blood pressure")),
    Sign("FITS", "RED", "दौरे / झटके / बेहोशी", "Convulsions / fits / unconscious",
         ("दौरा", "दौरे", "झटके", "बेहोश", "fits", "convulsion", "seizure", "daura", "behosh", "unconscious"), ("mother", "child")),
    Sign("HEADACHE_VISION", "RED", "तेज़ सिरदर्द / धुंधला दिखना", "Severe headache / blurred vision",
         ("तेज़ सिरदर्द", "तेज सिरदर्द", "धुंधला", "severe headache", "blurred", "dhundhla", "tez sirdard"), ("mother",)),
    Sign("WATER_BROKE", "RED", "पानी की थैली फटना / पानी आना", "Leaking fluid / water broke",
         ("पानी की थैली", "पानी आ", "water broke", "leaking", "pani aa", "thaili"), ("mother",)),
    Sign("SEVERE_ABDO", "RED", "पेट में तेज़ दर्द", "Severe abdominal pain",
         ("पेट में तेज़ दर्द", "पेट में तेज दर्द", "severe abdominal", "severe stomach", "pet me tez dard", "pet mein tez dard"), ("mother",)),
    Sign("NO_FETAL_MOVE", "RED", "बच्चे का हिलना कम/बंद", "Reduced or no fetal movement",
         ("हिलना बंद", "हिलना कम", "हलचल नहीं", "हलचल कम", "no movement", "reduced movement", "fetal movement", "hilna band", "hilna kam"), ("mother",)),
    Sign("BREATHING", "RED", "साँस लेने में तकलीफ़", "Difficulty breathing",
         ("साँस लेने में", "सांस लेने में", "साँस फूल", "सांस फूल", "difficulty breathing", "breathless", "short of breath", "saans lene", "saans phool", "sans phool"), ("mother", "child")),
    Sign("SWELLING", "YELLOW", "चेहरे/हाथ में सूजन", "Swelling of face/hands",
         ("सूजन", "swelling", "sujan", "soojan"), ("mother",)),
    Sign("FEVER", "YELLOW", "बुखार", "Fever",
         ("बुखार", "fever", "bukhar", "bukhaar"), ("mother", "child")),
    Sign("VOMITING", "YELLOW", "लगातार उल्टी", "Persistent vomiting",
         ("उल्टी", "vomit", "ulti"), ("mother", "child")),
    Sign("PALLOR", "YELLOW", "बहुत कमज़ोरी / पीलापन (खून की कमी)", "Severe weakness / pallor",
         ("पीलापन", "कमज़ोरी", "कमजोरी", "pale", "pallor", "weakness", "kamzori"), ("mother",)),
    # ---- Newborn / infant (HBNC) ---------------------------------------
    Sign("NOT_FEEDING", "RED", "दूध नहीं पी रहा / चूस नहीं पा रहा", "Not feeding / unable to suck",
         ("दूध नहीं", "चूस नहीं", "not feeding", "not sucking", "doodh nahi", "dudh nahi"), ("child",)),
    Sign("LETHARGY", "RED", "सुस्त / हिल-डुल नहीं रहा", "Lethargic / not moving",
         ("सुस्त", "lethargic", "sust", "not moving", "हिल-डुल नहीं", "हिलडुल नहीं"), ("child",)),
    Sign("CHEST_INDRAW", "RED", "पसली चलना / छाती धँसना", "Chest indrawing",
         ("पसली", "छाती धँस", "छाती धंस", "chest indrawing", "pasli"), ("child",)),
    Sign("COLD", "RED", "शरीर ठंडा", "Cold to touch (hypothermia)",
         ("ठंडा", "cold body", "thanda"), ("child",)),
    Sign("JAUNDICE", "YELLOW", "पीलिया (आँखें/त्वचा पीली)", "Jaundice",
         ("पीलिया", "jaundice", "piliya", "peeliya"), ("child",)),
    Sign("CORD", "YELLOW", "नाभि लाल / मवाद", "Umbilicus red / pus",
         ("नाभि", "मवाद", "umbilic", "cord", "pus", "nabhi"), ("child",)),
    Sign("DIARRHOEA", "YELLOW", "दस्त", "Diarrhoea",
         ("दस्त", "diarrh", "loose motion", "dast"), ("child",)),
]


@dataclass
class TriageResult:
    level: str
    signs: list[Sign] = field(default_factory=list)
    vitals_flags: list[str] = field(default_factory=list)

    @property
    def advice_hi(self) -> str:
        if self.level == "RED":
            return ("🔴 आपातकाल: तुरंत 108 एम्बुलेंस बुलाएँ और नज़दीकी FRU/CHC ले जाएँ। "
                    "रास्ते में ANM/PHC को सूचित करें।")
        if self.level == "YELLOW":
            return "🟡 24 घंटे के अंदर PHC / ANM के पास रेफ़र करें। हालत बिगड़े तो 108 बुलाएँ।"
        return "🟢 कोई खतरे का संकेत नहीं मिला। नियमित देखभाल जारी रखें। संदेह हो तो PHC से पूछें।"

    def to_text_hi(self) -> str:
        lines = [self.advice_hi]
        found = [s.label_hi for s in self.signs] + self.vitals_flags
        if found:
            lines.append("पहचाने गए संकेत: " + ", ".join(found))
        lines.append(DISCLAIMER_HI)
        return "\n".join(lines)


_NEG_AFTER = ("नहीं है", "नही है", "nahi hai", "nahin hai", "नहीं", "nahi")
_NEG_BEFORE = (" no ", " not ", "बिना ", "koi ")


def _bp(text: str) -> tuple[int, int] | None:
    m = re.search(r"(?:bp|बीपी)?\s*(\d{2,3})\s*/\s*(\d{2,3})", text)
    return (int(m.group(1)), int(m.group(2))) if m else None


def _temp(text: str) -> float | None:
    m = re.search(r"(\d{2,3}(?:\.\d)?)\s*(?:°|डिग्री|degree|f\b|°f)", text)
    return float(m.group(1)) if m else None


def _rr(text: str) -> int | None:
    m = re.search(r"(\d{2,3})\s*(?:/min|सांस प्रति मिनट|साँस प्रति मिनट|breaths)", text)
    return int(m.group(1)) if m else None


def _hb(text: str) -> float | None:
    m = re.search(r"(?:hb|एचबी|हीमोग्लोबिन)\s*[:=]?\s*(\d{1,2}(?:\.\d)?)", text)
    return float(m.group(1)) if m else None


def triage(text: str, kind: str = "mother", age_days: int | None = None) -> TriageResult:
    """kind: 'mother' or 'child'. age_days used for newborn breathing-rate cut-off."""
    t = " " + text.lower() + " "
    signs: list[Sign] = []
    for s in SIGNS:
        if kind not in s.applies_to:
            continue
        for kw in s.keywords:
            i = t.find(kw.lower())
            if i < 0:
                continue
            around = t[max(0, i - 8): i + len(kw) + 14]
            if any(x in around for x in s.exclude):
                continue
            after = t[i + len(kw): i + len(kw) + 12]
            before = t[max(0, i - 8): i]
            if any(n in after for n in _NEG_AFTER) or any(n in before for n in _NEG_BEFORE):
                continue
            signs.append(s)
            break
    flags: list[str] = []
    level = "GREEN"
    if signs:
        level = "RED" if any(s.level == "RED" for s in signs) else "YELLOW"

    def bump(new: str, flag: str):
        nonlocal level
        flags.append(flag)
        if new == "RED" or (new == "YELLOW" and level == "GREEN"):
            level = new

    bp = _bp(t)
    if bp and kind == "mother":
        sys_, dia = bp
        if sys_ >= 160 or dia >= 110:
            bump("RED", f"बहुत ऊँचा BP {sys_}/{dia}")
        elif sys_ >= 140 or dia >= 90:
            bump("YELLOW", f"ऊँचा BP {sys_}/{dia}")
    temp = _temp(t)
    if temp:
        f = temp if temp > 50 else temp * 9 / 5 + 32
        if kind == "child" and (age_days is None or age_days <= 60) and (f >= 99.5 or f < 95.9):
            bump("RED", f"नवजात तापमान {temp}")
        elif f >= 102.2:
            bump("YELLOW", f"तेज़ बुखार {temp}")
        elif f >= 100.4:
            bump("YELLOW", f"बुखार {temp}")
    rr = _rr(t)
    if rr and kind == "child":
        cutoff = 60 if (age_days is None or age_days < 60) else (50 if age_days < 365 else 40)
        if rr >= cutoff:
            bump("RED", f"तेज़ साँस {rr}/मिनट")
    hb = _hb(t)
    if hb is not None and kind == "mother":
        if hb < 7:
            bump("RED", f"गंभीर खून की कमी Hb {hb}")
        elif hb < 11:
            bump("YELLOW", f"खून की कमी Hb {hb}")
    return TriageResult(level=level, signs=signs, vitals_flags=flags)
