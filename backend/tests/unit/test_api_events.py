"""Tests del listado de eventos y descarga de evidencia."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from secuh.db.models import CameraRow, EventRow


def seed_camera_with_events(
    session_factory: sessionmaker[Session],
    count: int,
    snapshot_path: str | None = None,
) -> CameraRow:
    with session_factory() as session:
        camera = CameraRow(
            name=f"cam-{uuid4().hex[:6]}",
            source_type="usb",
            source_url="0",
        )
        session.add(camera)
        session.flush()
        base = datetime.now(UTC)
        for i in range(count):
            session.add(
                EventRow(
                    id=uuid4(),
                    camera_id=camera.id,
                    timestamp=base + timedelta(seconds=i),
                    confidence=0.8,
                    person_count=1,
                    snapshot_path=snapshot_path,
                    notified=True,
                )
            )
        session.commit()
        return camera


class TestListEvents:
    def test_requiere_autenticacion(self, client: TestClient) -> None:
        assert client.get("/api/events").status_code == 401

    def test_paginacion_y_orden_descendente(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed_camera_with_events(session_factory, count=25)

        page1 = logged_client.get("/api/events?page=1&page_size=10").json()
        page3 = logged_client.get("/api/events?page=3&page_size=10").json()

        assert page1["total"] == 25
        assert len(page1["items"]) == 10
        assert len(page3["items"]) == 5
        timestamps = [item["timestamp"] for item in page1["items"]]
        assert timestamps == sorted(timestamps, reverse=True)

    def test_filtro_por_camara(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        camera = seed_camera_with_events(session_factory, count=3)
        seed_camera_with_events(session_factory, count=2)

        response = logged_client.get(f"/api/events?camera_id={camera.id}").json()

        assert response["total"] == 3
        assert all(item["camera_name"] == camera.name for item in response["items"])


class TestEvidence:
    def test_snapshot_existente_se_sirve(
        self,
        logged_client: TestClient,
        session_factory: sessionmaker[Session],
        tmp_path: Path,
    ) -> None:
        snapshot = tmp_path / "captura.jpg"
        snapshot.write_bytes(b"\xff\xd8jpeg-bytes")
        seed_camera_with_events(session_factory, count=1, snapshot_path=str(snapshot))
        event_id = logged_client.get("/api/events").json()["items"][0]["id"]

        response = logged_client.get(f"/api/events/{event_id}/snapshot")

        assert response.status_code == 200
        assert response.headers["content-type"] == "image/jpeg"

    def test_evidencia_expirada_da_404(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed_camera_with_events(
            session_factory, count=1, snapshot_path="data/snapshots/no-existe.jpg"
        )
        event_id = logged_client.get("/api/events").json()["items"][0]["id"]

        assert logged_client.get(f"/api/events/{event_id}/snapshot").status_code == 404

    def test_evidencia_requiere_autenticacion(self, app: FastAPI) -> None:
        with TestClient(app) as anonymous:
            assert anonymous.get(f"/api/events/{uuid4()}/snapshot").status_code == 401
