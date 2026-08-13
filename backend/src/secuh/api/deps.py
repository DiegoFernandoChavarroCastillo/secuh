"""Dependencias compartidas de la API (estado de la app, sesión, usuario)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from secuh.api.security import SESSION_COOKIE, LoginRateLimiter, decode_session_token
from secuh.db.models import UserRow
from secuh.runtime.supervisor import CameraSupervisor
from secuh.settings import ServerSettings


def get_settings(request: Request) -> ServerSettings:
    return cast(ServerSettings, request.app.state.settings)


def get_supervisor(request: Request) -> CameraSupervisor:
    return cast(CameraSupervisor, request.app.state.supervisor)


def get_rate_limiter(request: Request) -> LoginRateLimiter:
    return cast(LoginRateLimiter, request.app.state.login_rate_limiter)


def get_session(request: Request) -> Iterator[Session]:
    factory = cast("sessionmaker[Session]", request.app.state.session_factory)
    with factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
SettingsDep = Annotated[ServerSettings, Depends(get_settings)]
SupervisorDep = Annotated[CameraSupervisor, Depends(get_supervisor)]
RateLimiterDep = Annotated[LoginRateLimiter, Depends(get_rate_limiter)]


def get_current_user(request: Request, session: SessionDep, settings: SettingsDep) -> UserRow:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "No autenticado")
    username = decode_session_token(token, settings.secret_key)
    if username is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sesión inválida o expirada")
    user = session.execute(select(UserRow).where(UserRow.username == username)).scalar_one_or_none()
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Usuario no existe")
    return user


CurrentUserDep = Annotated[UserRow, Depends(get_current_user)]
