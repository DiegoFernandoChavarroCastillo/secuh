"""Fixtures compartidas: app FastAPI con SQLite en memoria y sin hardware."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from secuh.api.app import create_app
from secuh.api.security import hash_password
from secuh.db.models import Base, UserRow
from secuh.runtime.supervisor import CameraSupervisor
from secuh.settings import ServerSettings


@pytest.fixture()
def session_factory() -> sessionmaker[Session]:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def settings(tmp_path: Path) -> ServerSettings:
    return ServerSettings(
        database_url="sqlite://",
        secret_key="clave-de-test-suficientemente-larga-para-hs256",
        admin_password="admin-password-test",
        data_dir=tmp_path / "data",
        console_notifier=True,
        ntfy_topic=None,
    )


class NoopSupervisor(CameraSupervisor):
    """Supervisor que no arranca hilos ni carga YOLO (para tests de API)."""

    def __init__(self) -> None:  # no llama a super: no necesita nada real
        self._online: set = set()

    @property
    def running_count(self) -> int:
        return 0

    def is_online(self, camera_id: object) -> bool:
        return camera_id in self._online

    def metrics(self, camera_id: object) -> None:
        return None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass


@pytest.fixture()
def app(settings: ServerSettings, session_factory: sessionmaker[Session]) -> FastAPI:
    return create_app(
        settings=settings, session_factory=session_factory, supervisor=NoopSupervisor()
    )


@pytest.fixture()
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture()
def logged_client(client: TestClient, session_factory: sessionmaker[Session]) -> TestClient:
    with session_factory() as session:
        session.add(UserRow(username="diego", password_hash=hash_password("clave-segura-1")))
        session.commit()
    response = client.post(
        "/api/auth/login", json={"username": "diego", "password": "clave-segura-1"}
    )
    assert response.status_code == 200
    return client
