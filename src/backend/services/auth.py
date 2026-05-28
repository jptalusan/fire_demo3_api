"""Auth service: bcrypt password hashing + JWT issuance + bearer dependency."""

from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
from fastapi import Depends, HTTPException, Request, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.config import settings
from db.session import get_db

ALGORITHM = "HS256"
ACCESS_TOKEN_TTL_HOURS = 6

bearer_scheme = HTTPBearer(auto_error=False)


def _normalize_password(secret: str | bytes) -> bytes:
    if isinstance(secret, bytes):
        secret = secret.decode("utf-8", errors="ignore")
    if not isinstance(secret, str):
        raise TypeError("Password must be a string")
    encoded = secret.encode("utf-8")
    # bcrypt input limit
    return encoded[:72]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_normalize_password(password), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(_normalize_password(password), password_hash.encode("utf-8"))


def create_token(user_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "exp": datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_TTL_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def _extract_token(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    scheme, _, credentials = authorization.partition(" ")
    if credentials:
        if scheme.lower() != "bearer":
            return None
        return credentials.strip() or None
    return authorization.strip() or None


def _decode_user_id(token: str) -> int:
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
    sub = payload.get("sub")
    if sub is None:
        raise ValueError("Token missing subject")
    return int(sub)


def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    db: Session = Depends(get_db),
) -> int:
    """Resolve user_id from Bearer header, cookie, or raise 401."""
    token = (
        credentials.credentials
        if credentials
        else _extract_token(request.headers.get("Authorization"))
        or request.cookies.get("auth_token")
    )
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing authorization header or auth cookie",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return _decode_user_id(token)
    except (JWTError, TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )
