from __future__ import annotations
from datetime import datetime, date, time, timedelta, timezone
from typing import Optional
import uuid

def _dtstamp_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _date_to_dt(d: date, hour: int = 9, minute: int = 0) -> datetime:
    # Local time "floating" is acceptable for hackathon; many clients interpret as local.
    return datetime(d.year, d.month, d.day, hour, minute)

def make_ics(
    title: str,
    due_date: date,
    description: str = "",
    duration_minutes: int = 30,
    start_hour: int = 9,
    start_minute: int = 0,
) -> str:
    uid = str(uuid.uuid4())
    dtstart = _date_to_dt(due_date, start_hour, start_minute)
    dtend = dtstart + timedelta(minutes=duration_minutes)

    def fmt(dt: datetime) -> str:
        # floating local time
        return dt.strftime("%Y%m%dT%H%M%S")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//SmartFlow360//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{_dtstamp_utc()}",
        f"DTSTART:{fmt(dtstart)}",
        f"DTEND:{fmt(dtend)}",
        f"SUMMARY:{_escape(title)}",
        f"DESCRIPTION:{_escape(description)}",
        "END:VEVENT",
        "END:VCALENDAR",
        ""
    ]
    return "\r\n".join(lines)

def _escape(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
