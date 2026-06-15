"""Authentication endpoints: register, login, portal-login."""

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.config import settings
from backend.schemas.auth import LoginRequest, PortalLoginRequest, RegisterRequest, TokenResponse
from backend.services.auth import (
    ACCESS_TOKEN_TTL_HOURS,
    create_token,
    get_current_user,
    hash_password,
    verify_password,
)
from db import crud
from db.session import get_db

router = APIRouter()


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    if crud.get_user(db, body.username):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="User already exists")
    user = crud.create_user(db, body.username, hash_password(body.password))
    return {"id": user.id, "username": user.username}


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, response: Response, db: Session = Depends(get_db)) -> TokenResponse:
    user = crud.get_user(db, body.username)
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username/password",
        )
    token = create_token(user.id)
    # Cookie attributes come from settings so a cross-domain deploy can flip them
    # without touching code. Cross-site needs samesite="none" + secure=True (HTTPS).
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_TTL_HOURS * 60 * 60,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
    )
    return TokenResponse(access_token=token)


@router.post("/portal-login", response_model=TokenResponse)
def portal_login(
    body: PortalLoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Issue a session for `username` without a password.

    Intended for deployments where an upstream portal has already authenticated
    the caller and the backend trusts that portal (network ACL, mTLS, or signed
    header upstream). **Enabled by default.** Set `PORTAL_AUTH_ENABLED=false`
    in the backend env to lock the endpoint down (it then returns 404 with no
    info leak).

    First call for a username auto-creates the user. A high-entropy random
    password hash is stored so the regular `/auth/login` route cannot be used
    to log in as a portal-created user with any guessable password.
    """
    if not settings.PORTAL_AUTH_ENABLED:
        # Explicit 404 rather than 403/501: indistinguishable from "route doesn't
        # exist" so a probe can't tell the feature is gated behind a flag.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")

    user = crud.get_user(db, body.username)
    if user is None:
        # Random 32-byte secret -> bcrypt hash. Not stored anywhere, not derivable.
        random_pw = secrets.token_urlsafe(32)
        user = crud.create_user(db, body.username, hash_password(random_pw))

    token = create_token(user.id)
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_TTL_HOURS * 60 * 60,
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
    )
    return TokenResponse(access_token=token)


@router.get("/me")
def me(user_id: int = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Return the authenticated user. Used by the SPA to check session on load."""
    user = crud.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return {"id": user.id, "username": user.username}


@router.post("/logout")
def logout(response: Response) -> dict:
    """Clear the auth cookie. Bearer-token clients just drop their token."""
    response.delete_cookie(
        key="auth_token",
        samesite=settings.COOKIE_SAMESITE,
        secure=settings.COOKIE_SECURE,
    )
    return {"status": "ok"}
