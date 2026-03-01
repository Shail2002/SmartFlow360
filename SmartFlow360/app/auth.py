from passlib.context import CryptContext
from datetime import datetime, timedelta
import secrets

pwd_context = CryptContext(
    schemes=["argon2"],
    deprecated="auto",
    argon2__memory_cost=65536,
    argon2__time_cost=3,
    argon2__parallelism=4
)

def hash_password(password: str) -> str:
    """Hash a password using argon2."""
    return pwd_context.hash(password)

def verify_password(plain_password:str, hashed_password:str) -> bool:
    """Verify a plain password against a hashed password."""
    return pwd_context.verify(plain_password, hashed_password)

def generate_session_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)

def is_session_valid(session_expires_at: datetime) -> bool:
    """Check if session is still valid."""
    if session_expires_at is None:
        return False
    return datetime.utcnow() < session_expires_at
#ffadaw