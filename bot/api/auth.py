"""JWT authentication for the API server."""

import logging
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

from bot.config import (
    API_SECRET_KEY,
    API_TOKEN_EXPIRE_MINUTES,
    API_USERNAME,
    API_PASSWORD,
    LOGIN_MAX_ATTEMPTS,
    LOGIN_WINDOW_SECONDS,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])

# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Pre-hash the configured password at import time so we only bcrypt once.
# bcrypt hard-limits passwords to 72 bytes (newer versions raise instead of
# silently truncating) — truncate explicitly with a warning so the API module
# never crashes at import regardless of bcrypt version.
def _bcrypt_safe_password(pw: str) -> str:
    raw = pw.encode("utf-8")
    if len(raw) > 72:
        logger.warning(
            "API_PASSWORD is longer than 72 bytes — bcrypt only uses the "
            "first 72 bytes. Consider using a shorter password."
        )
        raw = raw[:72]
    return raw.decode("utf-8", errors="ignore")


_hashed_password: str = pwd_context.hash(_bcrypt_safe_password(API_PASSWORD))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

ALGORITHM = "HS256"


# ---------------------------------------------------------------------------
# Login brute-force protection (per IP, in-memory)
# ---------------------------------------------------------------------------
_login_attempts: dict[str, list[float]] = defaultdict(list)
_last_login_cleanup: float = 0.0


def _check_login_rate_limit(request: Request) -> None:
    """Raise 429 if this IP has exceeded the login attempt budget."""
    global _last_login_cleanup
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = now - LOGIN_WINDOW_SECONDS
    attempts = [t for t in _login_attempts[ip] if t > window]
    _login_attempts[ip] = attempts
    if len(attempts) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many login attempts. Try again in {LOGIN_WINDOW_SECONDS // 60} minutes.",
        )
    attempts.append(now)
    _login_attempts[ip] = attempts
    # Periodic cleanup to prevent unbounded memory growth
    if now - _last_login_cleanup > 600:
        _last_login_cleanup = now
        stale = [k for k, v in _login_attempts.items() if not v or v[-1] < window]
        for k in stale:
            del _login_attempts[k]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int  # seconds


class TokenData(BaseModel):
    username: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=API_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, API_SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    """Dependency — extracts and validates the username from the JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, API_SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
@router.post("/login", response_model=Token)
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    """Authenticate with username/password and receive a JWT token."""
    _check_login_rate_limit(request)
    password_ok = pwd_context.verify(
        _bcrypt_safe_password(form_data.password), _hashed_password
    )
    if form_data.username != API_USERNAME or not password_ok:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    expires = timedelta(minutes=API_TOKEN_EXPIRE_MINUTES)
    access_token = _create_access_token(data={"sub": form_data.username}, expires_delta=expires)
    return Token(
        access_token=access_token,
        expires_in=API_TOKEN_EXPIRE_MINUTES * 60,
    )
