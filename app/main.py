from __future__ import annotations
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Cookie, Response, Form
from .auth import hash_password, verify_password, generate_session_token, is_session_valid
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from sqlmodel import Session, select
from datetime import date, datetime, timedelta
import json
import tempfile
import os

from .db import init_db, get_session
from .models import Account, Interaction, Task, EmailDraft, RiskAssessment
from .schemas import (
    AccountCreate, AccountOut,
    InteractionCreate, InteractionOut,
    AnalysisOut, AskRequest, AskResponse,
    TranscribeResponse, LoginRequest
)
from .ai import analyze_notes, answer_account_question, transcribe_audio
from .utils.ics import make_ics
from .settings import settings

class LoginRequest(BaseModel):
    email: str
    password: str

app = FastAPI(title="SmartFlow360", version="1.0.0")

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

@app.on_event("startup")
def _startup():
    init_db()

@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    """Render the main dashboard (protected)."""
    token = request.cookies.get("session_token")
    if not token:
        # Redirect to login if no session
        return RedirectResponse(url="/login")
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "openai_ready": settings.openai_api_key_present
    })

# ---------------------------
# Accounts
# ---------------------------

@app.post("/api/accounts", response_model=AccountOut)
def create_account(payload: AccountCreate, session: Session = Depends(get_session)):
    acc = Account(name=payload.name, industry=payload.industry)
    session.add(acc)
    session.commit()
    session.refresh(acc)
    return acc

@app.get("/api/accounts", response_model=list[AccountOut])
def list_accounts(session: Session = Depends(get_session)):
    return session.exec(select(Account).order_by(Account.created_at.desc())).all()

@app.get("/api/accounts/{account_id}", response_class=JSONResponse)
def account_detail(account_id: int, session: Session = Depends(get_session)):
    acc = session.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")

    interactions = session.exec(
        select(Interaction).where(Interaction.account_id == account_id).order_by(Interaction.created_at.desc())
    ).all()

    tasks = session.exec(
        select(Task).where(Task.account_id == account_id).order_by(Task.created_at.desc())
    ).all()

    # return a compact JSON for the UI
    return {
        "account": acc.model_dump(),
        "interactions": [i.model_dump() for i in interactions],
        "tasks": [t.model_dump() for t in tasks],
    }

# ---------------------------
# Interactions + Analysis
# ---------------------------

@app.post("/api/accounts/{account_id}/interactions", response_model=InteractionOut)
def create_interaction(account_id: int, payload: InteractionCreate, session: Session = Depends(get_session)):
    acc = session.get(Account, account_id)
    if not acc:
        raise HTTPException(404, "Account not found")

    inter = Interaction(account_id=account_id, source=payload.source, raw_text=payload.raw_text)
    session.add(inter)
    session.commit()
    session.refresh(inter)
    return inter

@app.post("/api/interactions/{interaction_id}/analyze", response_model=AnalysisOut)
def analyze_interaction(interaction_id: int, session: Session = Depends(get_session)):
    inter = session.get(Interaction, interaction_id)
    if not inter:
        raise HTTPException(404, "Interaction not found")

    acc = session.get(Account, inter.account_id)
    if not acc:
        raise HTTPException(404, "Account not found")

    result = analyze_notes(raw_text=inter.raw_text, account_name=acc.name, today=date.today())

    # Persist tasks
    tasks_out = []
    for t in result["tasks"]:
        # parse due_date
        dd = None
        if t.get("due_date"):
            try:
                dd = date.fromisoformat(t["due_date"])
            except Exception:
                dd = None

        task = Task(
            account_id=acc.id,
            interaction_id=inter.id,
            title=t["title"],
            due_date=dd,
            priority=t.get("priority", "Medium"),
            rationale=t.get("rationale", "")
        )
        session.add(task)
        session.commit()
        session.refresh(task)
        tasks_out.append(task)

    # Persist email draft
    email_obj = result["email"]
    draft = EmailDraft(
        account_id=acc.id,
        interaction_id=inter.id,
        subject=email_obj["subject"],
        body=email_obj["body"],
        simplified_body=email_obj.get("simplified_body"),
        busy_bullets_json=json.dumps(result.get("busy_bullets") or [])
    )
    session.add(draft)
    session.commit()
    session.refresh(draft)

    # Persist risk
    risk_obj = result["risk"]
    risk = RiskAssessment(
        account_id=acc.id,
        interaction_id=inter.id,
        score=int(risk_obj.get("score", 50)),
        reasons_json=json.dumps(risk_obj.get("reasons") or [])
    )
    session.add(risk)
    session.commit()
    session.refresh(risk)

    # Build response
    return {
        "summary": result["summary"],
        "busy_bullets": result["busy_bullets"],
        "next_actions": result["next_actions"],
        "tasks": [
            {
                "id": t.id,
                "title": t.title,
                "due_date": t.due_date,
                "priority": t.priority,
                "status": t.status,
                "rationale": t.rationale
            } for t in tasks_out
        ],
        "email_draft": {
            "id": draft.id,
            "subject": draft.subject,
            "body": draft.body,
            "simplified_body": draft.simplified_body,
            "busy_bullets": json.loads(draft.busy_bullets_json or "[]")
        },
        "risk": {
            "id": risk.id,
            "score": risk.score,
            "reasons": json.loads(risk.reasons_json or "[]")
        }
    }

@app.post("/api/tasks/{task_id}/complete")
def complete_task(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    task.status = "Done"
    session.add(task)
    session.commit()
    return {"ok": True}

@app.get("/api/tasks/{task_id}/ics")
def task_ics(task_id: int, session: Session = Depends(get_session)):
    task = session.get(Task, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
    if not task.due_date:
        raise HTTPException(400, "Task has no due_date; cannot create calendar reminder.")
    ics = make_ics(
        title=f"SmartFlow360: {task.title}",
        due_date=task.due_date,
        description=f"Priority: {task.priority}\n\nRationale: {task.rationale or ''}".strip(),
    )
    # write temp file for download
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".ics")
    tmp.write(ics.encode("utf-8"))
    tmp.close()
    return FileResponse(tmp.name, media_type="text/calendar", filename=f"smartflow360-task-{task.id}.ics")

# ---------------------------
# Q&A (account memory)
# ---------------------------

@app.post("/api/ask", response_model=AskResponse)
def ask(payload: AskRequest, session: Session = Depends(get_session)):
    acc = session.get(Account, payload.account_id)
    if not acc:
        raise HTTPException(404, "Account not found")

    interactions = session.exec(
        select(Interaction)
        .where(Interaction.account_id == payload.account_id)
        .order_by(Interaction.created_at.desc())
        .limit(4)
    ).all()

    tasks = session.exec(
        select(Task)
        .where(Task.account_id == payload.account_id)
        .order_by(Task.created_at.desc())
        .limit(8)
    ).all()

    context = []
    if interactions:
        context.append("Recent interactions:\n" + "\n\n".join(
            [f"- ({i.created_at.isoformat()}) {i.raw_text}" for i in interactions]
        ))
    if tasks:
        context.append("Recent tasks:\n" + "\n".join(
            [f"- [{t.status}] {t.title} (priority={t.priority}, due={t.due_date})" for t in tasks]
        ))

    answer = answer_account_question(
        question=payload.question,
        account_name=acc.name,
        context_blocks=context,
        mode=payload.mode
    )
    return {"answer": answer}

# ---------------------------
# Optional: server-side transcription
# ---------------------------

@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
    # Accept audio file upload and transcribe via OpenAI Audio API.
    # For the demo UI we use browser speech recognition, but this endpoint is available too.
    suffix = os.path.splitext(file.filename or "")[-1] or ".webm"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        text = transcribe_audio(tmp_path)
        return {"text": text}
    except Exception as e:
        raise HTTPException(400, f"Transcription failed: {e}")
    finally:
        try:
            os.remove(tmp_path)
        except Exception:
            pass

# ---------------------------
# Authentication Routes
# ---------------------------

@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request):
    """Render the login page."""
    return templates.TemplateResponse("login.html", {"request": request})

@app.post("/api/auth/register", response_model=dict)
def register(payload: AccountCreate, session: Session = Depends(get_session)
):
    """Register a new account with email and password."""
    # Checking if email already exists
    existing = session.exec(select(Account).where(Account.email == payload.email)).first()
    
    if existing:
        raise HTTPException(400, "Email already registered")
    
    # Create a new account with hashed password
    acc = Account(
        name=payload.name,
        email=payload.email,
        industry=payload.industry,
        password_hash=hash_password(payload.password),
        is_active=True
    )
    session.add(acc)
    session.commit()
    session.refresh(acc)

    return {
        "id": acc.id,
        "name": acc.name,
        "email": acc.email,
        "message": "Account created successfully. Please log in with a password."
    }

@app.post("/api/auth/login", response_model=dict)
def login(
    payload: LoginRequest,
    response: Response,
    session_dep: Session = Depends(get_session)
):
    """Login with email and password."""
    email = payload.email
    password = payload.password

    if not email or not password:
        raise HTTPException(400, "Email and password required.")

    
    # Find account by email
    acc = session_dep.exec(
        select(Account).where(Account.email == email)
    ).first()

    if not acc or not verify_password(password, acc.password_hash):
        raise HTTPException(401, "Invalid email or password")
    
    if not acc.is_active:
        raise HTTPException(403, "Account is inactive.")
    
    #Generate session token
    token = generate_session_token()
    acc.session_token = token
    acc.session_expires_at = datetime.utcnow() + timedelta(days=7)
    session_dep.add(acc)
    session_dep.commit()

    response.set_cookie(key="session_token", value=token, httponly=True)

    return {
        "id": acc.id,
        "name": acc.name,
        "email": acc.email,
        "session_token": token,
        "expires_in": 604800
    }

@app.post("/api/auth/logout", response_model=dict)
def logout(session_token: str,
           session_dep: Session = Depends(get_session)
):
    """Logout and invalidate session."""
    acc = session_dep.exec(select(Account).where(Account.session_token ==
                            session_token)
                            ).first()
    
    if acc:
        acc.session_token = None
        acc.session_expires_at = None
        session_dep.add(acc)
        session_dep.commit()

    return {"message": "Logged out successfully"}

@app.get("/api/auth/verify", response_model=dict)
def verify_session(
    session_token: str,
    session_dep: Session = Depends(get_session)
):
    """Verify if a session token is a valid."""
    acc = session_dep.exec(
        select(Account).where(Account.session_token == session_token)
    ).first()

    if not acc or not is_session_valid(acc.session_expires_at):
        raise HTTPException(401, "Invalid or expired session")
    
    return {
        "id": acc.id,
        "name": acc.name,
        "email": acc.email,
        "is_valid": True
    }