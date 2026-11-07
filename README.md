# ASHA Saathi · आशा साथी

**A Hindi-first AI agent for India's 10.4 lakh ASHA frontline health workers.**
It works on Telegram and on the web. It registers pregnant women and infants, works out every ANC check-up and vaccine due date from the national schedules, flags danger signs with fixed rules (it never diagnoses, and always refers to the PHC or 108), and gives each ASHA a ranked home-visit list for the day.

> Built for **Code for a Billion 2026** (Code for India), Health track, with **AgentFoundry**, the official IDE.
> Status: in active development (Nov 2026). Live demo and Telegram bot links are added here once deployed.

---

## The problem

- **10.40 lakh ASHAs** are the first point of contact for maternal and child health in India ([PIB, Sep 2026](https://www.pib.gov.in/PressNoteDetails.aspx?ModuleId=3&NoteId=160043&lang=1&reg=3)). Each one covers about 1,000 people.
- They track every pregnancy and every child's vaccines **from memory and paper registers**: 4 ANC visits, Td doses, a 9-visit vaccine schedule per child, and 6 HBNC newborn visits. A missed date is a missed vaccine or a missed high-risk pregnancy.
- The stakes: India still records a **maternal mortality ratio of 88 per lakh live births** (SRS 2020-22) and an **infant mortality rate of 24 per 1,000** (SRS 2024). Most of these deaths follow danger signs (bleeding, eclampsia, newborn sepsis) that were not caught or referred in time.

## What ASHA Saathi does

| Feature | How |
|---|---|
| 🗣️ Hindi / Hinglish chat | "नई गर्भवती सीता LMP 01-08-2026 गाँव रामपुर" - no forms, no English needed |
| 📅 Due dates | ANC 1-4, Td-1/Td-2, and the full UIP schedule (BCG to DPT-B2), computed from LMP / date of birth |
| 🚨 Danger-sign triage | 18 maternal and newborn danger signs plus BP, Hb, temperature and breathing-rate cut-offs → 🔴 call 108 now / 🟡 PHC within 24 h / 🟢 routine |
| 🏠 Daily visit list | Ranks today's homes: triage follow-ups, HBNC newborn days (3/7/14/21/28/42), overdue doses, 36+ week pregnancies |
| 📊 Dashboard | Live usage stats, today's visits and the beneficiary register |

### Safety by design
- **The LLM never makes a medical decision.** Groq (`openai/gpt-oss-120b`) only turns a free-text Hindi message into a small JSON tool call. Dates come from `app/schedules.py`; triage comes from `app/triage.py`. Both are plain, tested rules with cited sources ([docs/SOURCES.md](docs/SOURCES.md)).
- If the rules see a danger sign, triage wins over whatever the LLM parsed.
- Every triage reply says it is not a diagnosis and points to 108 or the PHC.
- Works without the LLM: slash commands and a rule-based Hindi parser keep the bot working if the API is down.
- Telegram ids are stored only as salted hashes. **The demo uses synthetic data only; do not enter real patient data.**

## Architecture

```
Telegram / Web chat ──► FastAPI (app/main.py)
                           │
                           ▼
                   Agent (app/agent.py)
          LLM intent → JSON tool call (Groq, small prompt)
          fallback: rule parser (Hindi/Hinglish/commands)
                           │
     ┌──────────────┬──────┴───────┬───────────────┐
     ▼              ▼              ▼               ▼
 register       schedules.py    triage.py      visits.py
 (db.py)        MoHFW ANC +     fixed danger   ranked daily
 SQLite/Postgres UIP NIS        sign rules     visit list
```

## Try it

```
मदद                                   → help
नई गर्भवती सीता LMP 01-08-2026 गाँव रामपुर  → register, EDD, next check-ups
नया बच्चा राजू जन्म 01-10-2026 माँ गीता      → register child, due vaccines
सीता की स्थिति                          → full schedule with status
सीता ANC2 हो गया                        → record a check-up / dose
सीता को तेज़ सिरदर्द और धुंधला दिख रहा है    → 🔴 call 108
आज की सूची                              → today's ranked home visits
```

## Run locally

```bash
git clone https://github.com/abidhussain19932-stack/asha-saathi
cd asha-saathi
pip install -r requirements.txt
pytest -q                       # 36 tests: schedules, triage, agent flow
uvicorn app.main:app --reload   # http://localhost:8000
```

Optional environment variables:

| Variable | Purpose |
|---|---|
| `GROQ_API_KEY` | free-tier Groq key for Hindi understanding (falls back to rules if absent) |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME` | Telegram bot from @BotFather |
| `PUBLIC_URL` | public base URL; the Telegram webhook is set to `PUBLIC_URL/telegram/webhook` on start |
| `DATABASE_URL` | Postgres (e.g. Neon free tier); default is local SQLite |

## Deploy (free)
`render.yaml` deploys the app as a Render free web service. Use a Neon free Postgres in `DATABASE_URL` so data survives restarts.

## Proven impact
Usage numbers on the dashboard and at `/api/stats` come straight from the deployed database: real test users, messages and triage checks, kept separate from the synthetic demo dataset. This section will be updated with the pilot figures before submission.

## Licence
MIT. See [LICENSE](LICENSE). Not a medical device; for decision support and training only.
