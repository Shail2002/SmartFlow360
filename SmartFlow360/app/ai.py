from __future__ import annotations
from typing import Any, Dict, List
from datetime import date
import json

from .settings import settings
from .schemas import smartflow_extract_json_schema
from .utils.text import heuristic_tasks, heuristic_summary, heuristic_email, heuristic_risk

def _openai_client():
    from openai import OpenAI
    return OpenAI()

def analyze_notes(
    raw_text: str,
    account_name: str,
    today: date,
) -> Dict[str, Any]:
    '''
    Returns a dict matching smartflow_extract_json_schema().
    Uses OpenAI Structured Outputs when OPENAI_API_KEY is set.
    Falls back to a heuristic extractor otherwise (so the app still runs).
    '''
    if not settings.openai_api_key_present:
        tasks = heuristic_tasks(raw_text)
        return {
            "summary": heuristic_summary(raw_text),
            "busy_bullets": ["Review recap", "Send follow-up email", "Schedule next call", "Share requested info", "Track next steps"][:5],
            "next_actions": [t["title"] for t in tasks][:5] or ["Send follow-up email", "Schedule next meeting"],
            "tasks": tasks,
            "email": heuristic_email(account_name),
            "risk": heuristic_risk(len(tasks)),
            "_fallback": True
        }

    client = _openai_client()
    schema = smartflow_extract_json_schema()

    system = (
        "You are SmartFlow360, an accessibility-first sales follow-up assistant. "
        "Turn messy meeting notes into clear follow-ups. "
        "Write in simple, direct language. Avoid jargon. "
        "For due_date: output YYYY-MM-DD if a date is mentioned or clearly implied; otherwise null. "
        "If the notes mention 'next week', pick a reasonable date 7 days from today. "
        "Always produce 1-5 busy_bullets (max 5) and 1-6 next_actions. "
        "Email body should be professional, concise, and include concrete next steps. "
        "Simplified_body must be dyslexia-friendly: short sentences, extra spacing, bullet points, no long paragraphs."
    )

    user = (
        f"Today's date is {today.isoformat()}.\n"
        f"Account: {account_name}\n\n"
        "Meeting notes:\n"
        f"{raw_text}\n\n"
        "Return the structured result."
    )

    response = client.responses.create(
        model=settings.smartflow_model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        text={
            "format": {
                "type": "json_schema",
                "name": "smartflow_extract",
                "schema": schema,
                "strict": True,
            }
        }
    )

    data = json.loads(response.output_text)

    # Light clamps
    data["busy_bullets"] = (data.get("busy_bullets") or [])[:5]
    data["next_actions"] = (data.get("next_actions") or [])[:6]
    data["tasks"] = (data.get("tasks") or [])[:10]
    return data

def answer_account_question(
    question: str,
    account_name: str,
    context_blocks: List[str],
    mode: str = "normal",
) -> str:
    if not settings.openai_api_key_present:
        return "AI is not configured (missing OPENAI_API_KEY). Add it to your .env and restart."

    client = _openai_client()

    style = {
        "normal": "Answer clearly and concretely.",
        "busy": "Give exactly 5 bullets. No paragraphs.",
        "simple": "Use very simple words and short sentences (dyslexia-friendly)."
    }.get(mode, "Answer clearly and concretely.")

    system = (
        "You are SmartFlow360 Q&A. Use ONLY the provided context. "
        "If the answer is not in context, say what is missing and ask one clarifying question. "
        + style
    )

    user = (
        f"Account: {account_name}\n\n"
        "Context:\n" + "\n\n---\n\n".join(context_blocks[:6]) + "\n\n"
        f"Question: {question}"
    )

    resp = client.responses.create(
        model=settings.smartflow_model,
        input=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    return resp.output_text.strip()

def transcribe_audio(file_path: str) -> str:
    '''Optional server-side transcription endpoint.'''
    if not settings.openai_api_key_present:
        raise RuntimeError("Missing OPENAI_API_KEY")

    client = _openai_client()
    with open(file_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            model=settings.transcribe_model,
            file=f,
            response_format="text",
        )
    return transcription.text
