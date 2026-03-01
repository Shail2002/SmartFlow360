from __future__ import annotations
import re
from datetime import date, timedelta

def heuristic_tasks(raw: str) -> list[dict]:
    # Fallback when no API key. Very simple extraction.
    lines = [ln.strip(" -\t") for ln in raw.splitlines() if ln.strip()]
    tasks = []
    # grab bullet-like lines
    for ln in lines:
        if re.match(r"^(todo|action|next|follow[- ]?up)[:\-]", ln, re.I) or ln.startswith(("*", "-", "•")):
            title = re.sub(r"^(todo|action|next|follow[- ]?up)[:\-]\s*", "", ln, flags=re.I)
            title = title.lstrip("*-• ").strip()
            if title:
                tasks.append({"title": title[:120], "due_date": None, "priority": "Medium", "rationale": "Heuristic extraction."})
    if not tasks:
        # default to first 2 lines
        for ln in lines[:2]:
            tasks.append({"title": ln[:120], "due_date": None, "priority": "Medium", "rationale": "Heuristic extraction."})
    return tasks[:6]

def heuristic_summary(raw: str) -> str:
    raw = re.sub(r"\s+", " ", raw).strip()
    return raw[:220] + ("..." if len(raw) > 220 else "")

def heuristic_email(account: str) -> dict:
    subject = f"Following up — next steps for {account}"
    body = (
        f"Hi there,\n\n"
        f"Thanks for the conversation. Sharing a quick recap and next steps.\n\n"
        f"- (Add recap here)\n"
        f"- (Add next steps here)\n\n"
        f"Does this work if we schedule a quick follow-up?\n\n"
        f"Best,\n"
        f""
    )
    simplified = (
        "Hi,\n\n"
        "Thanks for your time. Here are the next steps:\n"
        "- (Next step 1)\n"
        "- (Next step 2)\n\n"
        "Can we schedule a quick follow-up?\n\n"
        "Best,"
    )
    return {"subject": subject, "body": body, "simplified_body": simplified}

def heuristic_risk(tasks_count: int) -> dict:
    # Simple heuristic: more tasks -> need follow-up -> moderate risk.
    score = 60 if tasks_count >= 3 else 45
    reasons = ["No explicit next meeting scheduled.", "Follow-up tasks pending."]
    return {"score": score, "reasons": reasons[:3]}
