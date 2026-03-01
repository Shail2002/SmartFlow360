from __future__ import annotations
from typing import Optional
from datetime import datetime, date
from sqlmodel import SQLModel, Field, Column, String
from datetime import datetime
from typing import Optional
import secrets

class Account(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    email: str = Field(index=True, unique=True)
    password_hash: str
    is_active: bool = Field(default=True)
    industry: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    session_token: Optional[str] = Field(default=None, nullable=True)
    session_expires_at: Optional[datetime] = Field(default=None, nullable=True)

class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    email: str
    name: str
    picture: Optional[str]

class Contact(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True, foreign_key="account.id")
    name: str
    email: Optional[str] = None
    role: Optional[str] = None

class Interaction(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True, foreign_key="account.id")
    source: str = Field(default="notes")  # notes | voice
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
    raw_text: str

class Task(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True, foreign_key="account.id")
    interaction_id: int = Field(index=True, foreign_key="interaction.id")

    title: str
    due_date: Optional[date] = Field(default=None, index=True)
    priority: str = Field(default="Medium", index=True)  # High | Medium | Low
    status: str = Field(default="Open", index=True)      # Open | Done
    rationale: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class EmailDraft(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True, foreign_key="account.id")
    interaction_id: int = Field(index=True, foreign_key="interaction.id")

    subject: str
    body: str
    simplified_body: Optional[str] = None
    busy_bullets_json: Optional[str] = None  # JSON list[str]
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)

class RiskAssessment(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    account_id: int = Field(index=True, foreign_key="account.id")
    interaction_id: int = Field(index=True, foreign_key="interaction.id")

    score: int = Field(default=50, index=True)  # 0-100
    reasons_json: str = "[]"
    created_at: datetime = Field(default_factory=datetime.utcnow, index=True)
