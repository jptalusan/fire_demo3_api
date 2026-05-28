"""Authentication endpoints: register, login."""

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
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
    response.set_cookie(
        key="auth_token",
        value=token,
        httponly=True,
        max_age=ACCESS_TOKEN_TTL_HOURS * 60 * 60,
        samesite="lax",
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
    response.delete_cookie(key="auth_token", samesite="lax")
    return {"status": "ok"}
