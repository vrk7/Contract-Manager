from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

import jwt
import structlog
from fastapi import HTTPException, Query, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext

from .config import get_settings

logger = structlog.get_logger(__name__)

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer = HTTPBearer(auto_error=False)


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_context.verify(plain, hashed)


def create_access_token(user_id: str) -> str:
    settings = get_settings()
    expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    return jwt.encode(
        {"sub": user_id, "exp": expire},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )


def _decode_token(raw: str) -> str:
    """Verify JWT signature and return user_id (sub claim). Raises HTTPException on failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(raw, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
        user_id: str | None = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload")
        return user_id
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except jwt.PyJWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
) -> str | None:
    """
    Stateless JWT verification — returns user_id from token without a DB lookup.
    Returns None in in-memory/test mode so tests run without auth.
    Raises 401 when a real DB mode is active and no valid token is supplied.
    """
    settings = get_settings()
    if settings.in_memory_mode:
        return None
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return _decode_token(credentials.credentials)


async def get_current_user_id_from_query(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(_bearer),
    token: Optional[str] = Query(default=None, alias="token"),
) -> str | None:
    """
    Like get_current_user_id but also accepts ?token= for EventSource streams
    (EventSource cannot send custom headers).
    """
    settings = get_settings()
    if settings.in_memory_mode:
        return None
    raw = (credentials.credentials if credentials else None) or token
    if not raw:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return _decode_token(raw)
