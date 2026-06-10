from pydantic import BaseModel, Field


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=6, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class PortalLoginRequest(BaseModel):
    """Username-only login for callers behind a trusted upstream portal.

    Only accepted when PORTAL_AUTH_ENABLED=true. Username rules match register.
    """
    username: str = Field(min_length=3, max_length=64)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
