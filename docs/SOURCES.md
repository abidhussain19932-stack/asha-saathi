# Sources

Every schedule and rule in ASHA Saathi comes from a public Government of India source. The LLM never
computes a date or makes a medical decision.

## Antenatal care (app/schedules.py)
- MoHFW, *Guidelines for Antenatal Care and Skilled Attendance at Birth by ANMs/LHVs/SNs* (2010):
  minimum four ANC visits - 1st within 12 weeks (registration), 2nd 14-26 weeks, 3rd 28-34 weeks,
  4th 36 weeks to term.
- Pradhan Mantri Surakshit Matritva Abhiyan (PMSMA): free ANC on the 9th of every month at government facilities.
- EDD by Naegele's rule (LMP + 280 days).

## Immunisation (app/schedules.py)
- MoHFW National Immunization Schedule (Universal Immunization Programme), as listed on U-WIN:
  https://uwin.mohfw.gov.in/faq
- NHM National Immunization Schedule:
  https://nhm.gov.in/New_Updates_2018/NHM_Components/Immunization/report/National_%20Immunization_Schedule.pdf
- Birth: BCG, OPV-0, Hep B birth dose · 6 wk: OPV-1, Penta-1, Rota-1, fIPV-1, PCV-1 · 10 wk: OPV-2, Penta-2, Rota-2 ·
  14 wk: OPV-3, Penta-3, Rota-3, fIPV-2, PCV-2 · 9-12 mo: MR-1, JE-1*, PCV-B, fIPV-3 · 16-24 mo: MR-2, JE-2*, DPT-B1, OPV-B ·
  5-6 yr: DPT-B2 · pregnant women: Td-1, Td-2 (4 weeks later) or Td-booster. *JE in endemic districts.

## Danger signs (app/triage.py)
- MoHFW / NHSRC ASHA Training Modules 6 & 7 (maternal and newborn danger signs).
- MoHFW Home Based Newborn Care (HBNC) operational guidelines (visit days 3, 7, 14, 21, 28, 42; newborn danger signs
  incl. temperature >= 37.5 C or < 35.5 C, fast breathing >= 60/min, chest indrawing, not feeding, lethargy).
- WHO/IMNCI fast-breathing cut-offs: >= 60/min (< 2 months), >= 50/min (2-12 months), >= 40/min (1-5 years).
- Hypertension in pregnancy: BP >= 140/90 refer; >= 160/110 emergency. Severe anaemia: Hb < 7 g/dL.

## Problem size and severity (README)
- ASHAs: "over 10.40 lakh ASHAs" - PIB press note, Ministry of Rural Development, 20 Sep 2026:
  https://www.pib.gov.in/PressNoteDetails.aspx?ModuleId=3&NoteId=160043&lang=1&reg=3
  (10.29 lakh as of 30 Jun 2024 - MoHFW Annual Report 2024-25; PIB PRID 2045385.)
- Maternal Mortality Ratio 88 per lakh live births (SRS 2020-22) - Rajya Sabha Unstarred Q 2676, 12 Aug 2025:
  https://sansad.in/getFile/annex/268/AU2676_k3eJh9.pdf
- IMR 24, NMR 18, U5MR 28 per 1,000 live births (SRS 2024) - NHM Child Health page.
