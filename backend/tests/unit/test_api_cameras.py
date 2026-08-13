"""Tests del CRUD de cámaras y armado/desarmado."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from secuh.db.models import EventRow

CAMERA = {
    "name": "entrada",
    "zone": "puerta principal",
    "source_type": "ip_webcam",
    "source_url": "http://192.168.1.50:8080/video",
}


def create(client: TestClient, **overrides: object) -> dict:
    response = client.post("/api/cameras", json={**CAMERA, **overrides})
    assert response.status_code == 201, response.text
    return response.json()


class TestCrud:
    def test_requiere_autenticacion(self, client: TestClient) -> None:
        assert client.get("/api/cameras").status_code == 401
        assert client.post("/api/cameras", json=CAMERA).status_code == 401

    def test_crear_y_listar(self, logged_client: TestClient) -> None:
        created = create(logged_client)

        cameras = logged_client.get("/api/cameras").json()

        assert [c["id"] for c in cameras] == [created["id"]]
        assert created["state"] == "disarmed"
        assert created["online"] is False

    def test_nombre_duplicado_da_409(self, logged_client: TestClient) -> None:
        create(logged_client)
        response = logged_client.post("/api/cameras", json=CAMERA)
        assert response.status_code == 409

    def test_editar_parcialmente(self, logged_client: TestClient) -> None:
        created = create(logged_client)

        response = logged_client.patch(
            f"/api/cameras/{created['id']}", json={"confidence_threshold": 0.7}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["confidence_threshold"] == 0.7
        assert body["name"] == "entrada"  # lo no enviado no cambia

    def test_borrar(self, logged_client: TestClient) -> None:
        created = create(logged_client)

        assert logged_client.delete(f"/api/cameras/{created['id']}").status_code == 204
        assert logged_client.get("/api/cameras").json() == []

    def test_borrar_camara_con_eventos_asociados(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        created = create(logged_client)
        with session_factory() as session:
            session.add(
                EventRow(
                    id=uuid4(),
                    camera_id=UUID(created["id"]),
                    timestamp=datetime.now(UTC),
                    confidence=0.9,
                    person_count=1,
                    notified=True,
                )
            )
            session.commit()

        response = logged_client.delete(f"/api/cameras/{created['id']}")

        assert response.status_code == 204
        assert logged_client.get("/api/cameras").json() == []

    def test_camara_inexistente_da_404(self, logged_client: TestClient) -> None:
        missing = "00000000-0000-0000-0000-000000000000"
        assert logged_client.patch(f"/api/cameras/{missing}", json={}).status_code == 404


class TestArmDisarm:
    def test_armar_y_desarmar(self, logged_client: TestClient) -> None:
        created = create(logged_client)

        armed = logged_client.post(f"/api/cameras/{created['id']}/arm").json()
        assert armed["state"] == "armed"

        disarmed = logged_client.post(f"/api/cameras/{created['id']}/disarm").json()
        assert disarmed["state"] == "disarmed"


class TestSecurityRedaction:
    def test_la_url_con_credenciales_se_devuelve_redactada(self, logged_client: TestClient) -> None:
        created = create(
            logged_client,
            name="patio",
            source_type="rtsp",
            source_url="rtsp://admin:secreta@192.168.1.60:554/s1",
        )

        assert "secreta" not in created["source_url_redacted"]
        assert "source_url" not in created  # la URL cruda jamás sale de la API
