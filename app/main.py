from __future__ import annotations

import os
import json
import tempfile
import smtplib
from fastapi import HTTPException
import ssl, smtplib
from email.message import EmailMessage
import io
from datetime import date
from email.message import EmailMessage
from typing import Optional, Any

from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request, Cookie, Response, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from .auth import hash_password, verify_password, generate_session_token, is_session_valid

from pydantic import BaseModel
from pypdf import PdfReader
from docx import Document
from starlette.middleware.sessions import SessionMiddleware
from reportlab.lib.pagesizes import LETTER
from reportlab.pdfgen import canvas

from sqlmodel import Session, select
from datetime import date, datetime, timedelta

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


# ---------------------------
# App
# ---------------------------
app = FastAPI(title="SmartFlow360", version="1.0.0")

# CORS (for Chrome extension + dev tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # hackathon/dev only (lock down later)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Sessions (used only if you later enable login)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "supersecret"),
    same_site="lax",
    https_only=False,  # set True when you use HTTPS in production
)

BASE_DIR = os.path.dirname(__file__)
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


# ---------------------------
# Auth helper (optional)
# NOTE: Your current project doesn't have OAuth routes here.
# This helper is only used in /api/extract below (currently protected).
# If you want extract to work without login, remove user=Depends(get_current_user).
# ---------------------------
def get_current_user(request: Request):
    user = request.session.get("user")
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated. Please login.")
    return user


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


# ---------------------------
# Tasks
# ---------------------------
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
# File extract (PDF/DOCX/TXT)
# NOTE: currently protected. For extension demo, remove auth.
# ---------------------------
@app.post("/api/extract")
async def extract_file(file: UploadFile = File(...)):
    data = await file.read()
    filename = file.filename or "upload"
    ext = os.path.splitext(filename.lower())[1]
    extracted = ""

    if ext == ".pdf":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            reader = PdfReader(tmp_path)
            parts = []
            for page in reader.pages:
                txt = page.extract_text() or ""
                if txt.strip():
                    parts.append(txt)
            extracted = "\n\n".join(parts).strip()
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    elif ext == ".docx":
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
            tmp.write(data)
            tmp_path = tmp.name
        try:
            doc = Document(tmp_path)
            extracted = "\n".join([p.text for p in doc.paragraphs]).strip()
        finally:
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    else:
        try:
            extracted = data.decode("utf-8")
        except Exception:
            extracted = data.decode("utf-8", errors="ignore")
        extracted = extracted.strip()

    if not extracted:
        raise HTTPException(
            status_code=400,
            detail="Could not extract text. If this is a scanned PDF (image), text extraction will be empty.",
        )

    MAX_CHARS = 20000
    truncated = False
    if len(extracted) > MAX_CHARS:
        extracted = extracted[:MAX_CHARS]
        truncated = True

    return {
        "filename": filename,
        "chars": len(extracted),
        "truncated": truncated,
        "text": extracted,
    }


# ---------------------------
# Optional: server-side transcription
# ---------------------------
@app.post("/api/transcribe", response_model=TranscribeResponse)
async def transcribe(file: UploadFile = File(...)):
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

# ============================================================
# Chrome Extension endpoints (do not depend on accounts UI)
# ============================================================

class ExtensionAnalyzeRequest(BaseModel):
    text: str
    title: Optional[str] = None

@app.post("/api/ext/analyze")
def ext_analyze(payload: ExtensionAnalyzeRequest):
    if not payload.text or not payload.text.strip():
        raise HTTPException(400, "text is required")
    result = analyze_notes(
        raw_text=payload.text,
        account_name=payload.title or "Chrome Extension",
        today=date.today()
    )
    return result


class EmailReportRequest(BaseModel):
    to_email: str
    subject: str
    summary: str
    full_json: dict[str, Any]

def build_pdf_report(subject: str, summary: str, full_json: dict) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=LETTER)
    width, height = LETTER

    y = height - 60
    c.setFont("Helvetica-Bold", 14)
    c.drawString(50, y, subject)
    y -= 30

    c.setFont("Helvetica", 10)
    for line in (summary or "").splitlines():
        c.drawString(50, y, line[:120])
        y -= 14
        if y < 70:
            c.showPage()
            y = height - 60

    c.showPage()
    c.setFont("Helvetica", 9)
    c.drawString(50, height - 60, "Full JSON (truncated view):")

    text = json.dumps(full_json, indent=2)[:6000]
    y = height - 80
    for line in text.splitlines():
        c.drawString(50, y, line[:120])
        y -= 12
        if y < 70:
            c.showPage()
            y = height - 60

    c.save()
    return buf.getvalue()

@app.post("/api/ext/email-report")
def ext_email_report(payload: EmailReportRequest):
    # build PDF bytes
    pdf_bytes = build_pdf_report(payload.subject, payload.summary, payload.full_json)

    # build email message
    msg = EmailMessage()
    msg["From"] = os.getenv("EMAIL_FROM", "smartflow360@demo.com")
    msg["To"] = payload.to_email
    msg["Subject"] = payload.subject or "SmartFlow360 report"
    msg.set_content(payload.summary or "SmartFlow360 report attached.")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="smartflow360-report.pdf")

    # SMTP config
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "465"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")

    if not host or not user or not pw:
        raise HTTPException(status_code=500, detail="SMTP is not configured in .env")

    context = ssl.create_default_context()

    try:
        if port == 465:
            # SSL
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as s:
                s.login(user, pw)
                s.send_message(msg)
        else:
            # STARTTLS (587)
            with smtplib.SMTP(host, port, timeout=20) as s:
                s.ehlo()
                s.starttls(context=context)
                s.ehlo()
                s.login(user, pw)
                s.send_message(msg)
    except smtplib.SMTPAuthenticationError as e:
        raise HTTPException(status_code=500, detail=f"SMTP auth failed: {e}")
    except smtplib.SMTPException as e:
        raise HTTPException(status_code=500, detail=f"SMTP error: {e}")

    return {"ok": True}

@app.post("/api/ext/email-report")
def ext_email_report(payload: EmailReportRequest):
    if not payload.to_email:
        raise HTTPException(400, "to_email is required")

    pdf_bytes = build_pdf_report(payload.subject, payload.summary, payload.full_json)

    msg = EmailMessage()
    msg["From"] = os.getenv("EMAIL_FROM", "smartflow360@demo.com")
    msg["To"] = payload.to_email
    msg["Subject"] = payload.subject or "SmartFlow360 report"
    msg.set_content(payload.summary or "SmartFlow360 report attached.")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename="smartflow360-report.pdf")

    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw = os.getenv("SMTP_PASS")

    if not host or not user or not pw:
        raise HTTPException(500, "SMTP is not configured in .env (SMTP_HOST/SMTP_USER/SMTP_PASS).")

    with smtplib.SMTP(host, port) as s:
        s.starttls()
        s.login(user, pw)
        s.send_message(msg)

    return {"ok": True}