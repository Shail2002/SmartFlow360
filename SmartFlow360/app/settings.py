from __future__ import annotations
from pydantic import BaseModel
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseModel):
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./smartflow360.db")
    openai_api_key_present: bool = bool(os.getenv("OPENAI_API_KEY"))
    smartflow_model: str = os.getenv("SMARTFLOW_MODEL", "gpt-4o-mini")
    transcribe_model: str = os.getenv("SMARTFLOW_TRANSCRIBE_MODEL", "gpt-4o-mini-transcribe")

settings = Settings()
#fajwiajd
