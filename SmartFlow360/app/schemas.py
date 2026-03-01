from __future__ import annotations
from typing import Optional, List, Literal, Dict, Any
from datetime import date, datetime
from pydantic import BaseModel, Field, EmailStr

Priority = Literal["High", "Medium", "Low"]

class AccountCreate(BaseModel):
    name: str # = Field(min_length=1)
    email: str
    industry: str
    password: str
    #industry: Optional[str] = None

class LoginRequest(BaseModel):
    email: str
    password: str

class AuthResponse(BaseModel):
    id: int
    name: str
    email: str
    session_token: str
    expires_in: int

class AccountOut(BaseModel):
    id: Optional[int]
    name: str
    industry: Optional[str]
    created_at: datetime

class InteractionCreate(BaseModel):
    raw_text: str # = Field(min_length=1)
    # source: Literal["notes", "voice"] = "notes"
    source: str

class InteractionOut(BaseModel):
    id: Optional[int]
    account_id: int
    source: str
    created_at: datetime
    raw_text: str

class TaskOut(BaseModel):
    id: int
    title: str
    due_date: Optional[date]
    priority: str
    status: str
    rationale: Optional[str]

class EmailDraftOut(BaseModel):
    id: int
    subject: str
    body: str
    simplified_body: Optional[str]
    busy_bullets: List[str] = []

class RiskOut(BaseModel):
    id: int
    score: int
    reasons: List[str] = []

class AnalysisOut(BaseModel):
    summary: str
    busy_bullets: List[str]
    next_actions: List[str]
    tasks: List[TaskOut]
    email_draft: EmailDraftOut
    risk: RiskOut

class AskRequest(BaseModel):
    account_id: int
    question: str = Field(min_length=1)
    mode: Literal["normal", "busy", "simple"] = "normal"

class AskResponse(BaseModel):
    answer: str

class TranscribeResponse(BaseModel):
    text: str

def smartflow_extract_json_schema() -> Dict[str, Any]:
    # JSON schema for OpenAI structured output (subset-friendly).
    # Dates: YYYY-MM-DD or null.
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "summary": {"type": "string"},
            "busy_bullets": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 5
            },
            "next_actions": {
                "type": "array",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 6
            },
            "tasks": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "title": {"type": "string"},
                        "due_date": {"type": ["string", "null"], "description": "YYYY-MM-DD or null"},
                        "priority": {"type": "string", "enum": ["High", "Medium", "Low"]},
                        "rationale": {"type": "string"}
                    },
                    "required": ["title", "due_date", "priority", "rationale"]
                }
            },
            "email": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "simplified_body": {"type": "string"}
                },
                "required": ["subject", "body", "simplified_body"]
            },
            "risk": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "score": {"type": "integer", "minimum": 0, "maximum": 100},
                    "reasons": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": 6}
                },
                "required": ["score", "reasons"]
            }
        },
        "required": ["summary", "busy_bullets", "next_actions", "tasks", "email", "risk"]
    }
