from __future__ import annotations
from sqlmodel import SQLModel, create_engine, Session
from .settings import settings

# For SQLite + FastAPI:
connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, echo=False, connect_args=connect_args)

def init_db() -> None:
    SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session
