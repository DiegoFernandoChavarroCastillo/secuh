"""Autenticación: login/logout con cookie de sesión HttpOnly."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from sqlalchemy import select

from secuh.api.deps import CurrentUserDep, RateLimiterDep, SessionDep, SettingsDep
from secuh.api.schemas import LoginRequest, UserOut
from secuh.api.security import (
    SESSION_COOKIE,
    create_session_token,
    verify_password,
)
from secuh.db.models import UserRow

router = APIRouter(prefix="/auth", tags=["auth"])


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=UserOut)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    limiter: RateLimiterDep,
) -> UserOut:
    key = _client_key(request)
    if limiter.is_blocked(key):
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "Demasiados intentos fallidos; espera unos minutos",
        )

    user = session.execute(
        select(UserRow).where(UserRow.username == body.username)
    ).scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        limiter.register_failure(key)
        # Mismo mensaje exista o no el usuario: no filtrar cuáles existen.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciales inválidas")

    limiter.reset(key)
    token = create_session_token(user.username, settings.secret_key, settings.session_ttl_hours)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        httponly=True,
        samesite="lax",
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return UserOut(username=user.username)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


@router.get("/me", response_model=UserOut)
def me(user: CurrentUserDep) -> UserOut:
    return UserOut(username=user.username)
