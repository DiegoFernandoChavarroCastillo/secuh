"""Fábrica de la aplicación FastAPI.

Un solo proceso sirve la API y corre los workers de detección (vía el
supervisor). Las migraciones se aplican ANTES de arrancar (``alembic upgrade
head``, ver deploy/); la app no crea tablas.

Arranque: ``uvicorn secuh.api.app:create_app --factory``
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from secuh import __version__ as secuh_version
from secuh.api.routers import auth, cameras, channels, events, stream
from secuh.api.schemas import HealthOut
from secuh.api.security import LoginRateLimiter, hash_password
from secuh.core.ports import Notifier
from secuh.db.models import UserRow
from secuh.db.session import make_session_factory
from secuh.logging_setup import setup_logging
from secuh.notifications.console import ConsoleNotifier
from secuh.notifications.ntfy import NtfyNotifier
from secuh.runtime.supervisor import CameraSupervisor
from secuh.settings import ServerSettings
from secuh.storage.retention import RetentionJob

logger = logging.getLogger(__name__)


def build_notifiers(settings: ServerSettings) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if settings.console_notifier:
        notifiers.append(ConsoleNotifier())
    if settings.ntfy_topic:
        notifiers.append(NtfyNotifier(topic_url=settings.ntfy_topic))
    return notifiers


def bootstrap_admin(session_factory: sessionmaker[Session], settings: ServerSettings) -> None:
    """Crea el usuario admin inicial si la tabla de usuarios está vacía."""
    with session_factory() as session:
        count = session.execute(select(func.count()).select_from(UserRow)).scalar_one()
        if count > 0:
            return
        if not settings.admin_password:
            logger.warning(
                "No hay usuarios y SECUH_ADMIN_PASSWORD no está definida: "
                "el panel será inaccesible hasta configurarla y reiniciar"
            )
            return
        session.add(
            UserRow(
                username=settings.admin_user,
                password_hash=hash_password(settings.admin_password),
            )
        )
        session.commit()
        logger.info("Usuario admin inicial creado", extra={"username": settings.admin_user})


def create_app(
    settings: ServerSettings | None = None,
    session_factory: sessionmaker[Session] | None = None,
    supervisor: CameraSupervisor | None = None,
) -> FastAPI:
    """Los parámetros permiten inyectar dobles en tests; en producción se
    construye todo desde las variables de entorno."""
    setup_logging()
    settings = settings or ServerSettings()
    session_factory = session_factory or make_session_factory(settings.database_url)
    supervisor = supervisor or CameraSupervisor(
        session_factory=session_factory,
        settings=settings,
        notifiers=build_notifiers(settings),
    )
    retention = RetentionJob(data_dir=settings.data_dir, retention_days=settings.retention_days)

    if settings.secret_key == "dev-only-insecure-secret":
        logger.warning("SECUH_SECRET_KEY no está definida: usando clave de desarrollo insegura")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        bootstrap_admin(session_factory, settings)
        supervisor.start()
        retention.start()
        yield
        supervisor.stop()
        retention.stop()

    app = FastAPI(title="secuh", version=secuh_version, lifespan=lifespan)
    app.state.settings = settings
    app.state.session_factory = session_factory
    app.state.supervisor = supervisor
    app.state.login_rate_limiter = LoginRateLimiter(
        max_attempts=settings.login_max_attempts,
        lockout_seconds=settings.login_lockout_seconds,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth.router, prefix="/api")
    app.include_router(cameras.router, prefix="/api")
    app.include_router(channels.router, prefix="/api")
    app.include_router(events.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")

    @app.get("/api/health", response_model=HealthOut, tags=["health"])
    def health() -> HealthOut:
        return HealthOut(status="ok", cameras_running=supervisor.running_count)

    _mount_frontend(app, settings)
    return app


def _mount_frontend(app: FastAPI, settings: ServerSettings) -> None:
    """Sirve el panel compilado en "/" si existe (despliegue empaquetado).

    Las rutas /api/* ya están registradas y tienen prioridad; cualquier otra
    ruta devuelve index.html (SPA con rutas del lado del cliente).
    """
    dist = settings.frontend_dist
    if dist is None or not dist.is_dir():
        return
    index = dist / "index.html"
    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        return FileResponse(index)

    logger.info("Panel web servido desde %s", dist)
