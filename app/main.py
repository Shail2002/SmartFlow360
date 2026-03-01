from __future__ import annotations
from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pypdf import PdfReader
from docx import Document
from starlette.middleware.sessions import SessionMiddleware
from sqlmodel import Session, select
from datetime import date
import json
import tempfile
import os

from .db import init_db, get_session
from .models import Account, Interaction, Task, EmailDraft, RiskAssessment
from .schemas import (
    AccountCreate, AccountOut,
    InteractionCreate, InteractionOut,
    AnalysisOut, AskRequest, AskResponse,
    TranscribeResponse
)
from .ai import analyze_notes, answer_account_question, transcribe_audio
from .utils.ics import make_ics
from .settings import settings

app = FastAPI(title="SmartFlow360", version="1.0.0")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("SESSION_SECRET", "supersecret"),
    same_site="lax",
    https_only=False,  # set True when you use HTTPS in production
)

app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "templates"))

# ---------------------------
# Auth helper (MUST be above protected routes)
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

@app.post("/api/extract")
async def extract_file(file: UploadFile = File(...)):
    # Read file bytes
    data = await file.read()
    filename = file.filename or "upload"
    ext = os.path.splitext(filename.lower())[1]

    extracted = ""

    # PDF
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

    # DOCX
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

    # Plain text / JSON / CSV / MD
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

    # Safety: cap huge files so the AI prompt doesn't explode
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
