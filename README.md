# SmartFlow360 (SmartFollow accessibility track)

A hackathon-ready **mini CRM** that turns messy notes (or voice transcripts) into:
- action items (tasks)
- due dates + priorities
- follow-up email drafts
- .ics calendar reminders
- a risk score + reasons
- an “Explain like I’m busy” 5-bullet summary

## 1) Setup (VS Code)
### Create a venv
```bash
cd smartflow360
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
```

### Install deps
```bash
pip install -r requirements.txt
```

### Configure env
```bash
cp .env.example .env
# set OPENAI_API_KEY in .env
```

### Run
```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

> If you don't set `OPENAI_API_KEY`, the app still runs, but AI features return a helpful error message.

## 2) What to demo (5 minutes)
1. Create an account
2. Paste messy notes OR use Voice dictation
3. Click **Analyze**
4. Show: tasks, due dates, email draft, risk score
5. Download the calendar `.ics` and show “Explain like I’m busy”

## 3) Project structure
- `app/main.py` FastAPI routes + UI
- `app/ai.py` OpenAI calls (structured JSON schema)
- `app/models.py` SQLModel database tables
- `app/db.py` DB engine/session
- `app/utils/ics.py` calendar reminder generation
- `app/static/*` accessible UI (WCAG-ish, high contrast, keyboard-friendly)

# SmartFlow360
