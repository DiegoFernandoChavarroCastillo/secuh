"""Tests de la API de escena: conteos, filtro por clase y exportación a CSV."""

from __future__ import annotations

import csv
import io
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from secuh.db.models import CameraRow, EventObjectRow, EventRow


def seed(
    session_factory: sessionmaker[Session],
    scene_labels: tuple[str, ...] = ("dog", "car"),
    camera_name: str | None = None,
    camera_zone: str = "puerta",
) -> tuple[CameraRow, EventRow]:
    with session_factory() as session:
        camera = CameraRow(
            name=camera_name or f"cam-{uuid4().hex[:6]}",
            zone=camera_zone,
            source_type="usb",
            source_url="0",
        )
        session.add(camera)
        session.flush()
        event = EventRow(
            id=uuid4(),
            camera_id=camera.id,
            timestamp=datetime.now(UTC),
            confidence=0.9,
            person_count=1,
            notified=True,
            frame_width=640,
            frame_height=480,
            objects=[
                EventObjectRow(
                    source=EventObjectRow.SOURCE_TRIGGER,
                    label="person",
                    confidence=0.9,
                    x1=10,
                    y1=10,
                    x2=110,
                    y2=210,
                ),
                *[
                    EventObjectRow(
                        source=EventObjectRow.SOURCE_SCENE,
                        label=label,
                        confidence=0.7,
                        x1=20,
                        y1=20,
                        x2=120,
                        y2=120,
                    )
                    for label in scene_labels
                ],
            ],
        )
        session.add(event)
        session.commit()
        session.refresh(camera)
        session.refresh(event)
        return camera, event


def read_csv(body: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(body)))


class TestConteosEnElListado:
    def test_el_listado_trae_los_objetos_de_la_escena(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, scene_labels=("dog", "car", "car"))

        [item] = logged_client.get("/api/events").json()["items"]

        assert item["object_counts"] == {"dog": 1, "car": 2}

    def test_las_filas_trigger_no_se_cuentan_como_escena(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, scene_labels=("person", "dog"))

        [item] = logged_client.get("/api/events").json()["items"]

        # La persona del barrido cuenta una vez; la fila `trigger` es la misma
        # persona vista por el pipeline y sumarla la contaría dos veces.
        assert item["object_counts"]["person"] == 1


class TestFiltroPorClase:
    def test_filtra_eventos_por_etiqueta(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, scene_labels=("dog",))
        seed(session_factory, scene_labels=("car",))

        con_perro = logged_client.get("/api/events?label=dog").json()
        con_auto = logged_client.get("/api/events?label=car").json()
        sin_filtro = logged_client.get("/api/events").json()

        assert con_perro["total"] == 1
        assert con_auto["total"] == 1
        assert sin_filtro["total"] == 2

    def test_etiqueta_inexistente_devuelve_vacio(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory)

        page = logged_client.get("/api/events?label=elephant").json()

        assert page["total"] == 0
        assert page["items"] == []

    def test_filtro_por_rango_de_fechas(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory)
        futuro = (datetime.now(UTC) + timedelta(days=1)).isoformat()

        # Vía params, no interpolando: el "+00:00" del offset se leería como
        # un espacio si va sin codificar en la query string.
        page = logged_client.get("/api/events", params={"from": futuro}).json()

        assert page["total"] == 0


class TestDetalleDeEvento:
    def test_devuelve_las_cajas_y_la_resolucion(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        _, event = seed(session_factory, scene_labels=("dog",))

        detail = logged_client.get(f"/api/events/{event.id}").json()

        assert detail["frame_width"] == 640
        assert detail["frame_height"] == 480
        [obj] = detail["objects"]
        assert obj["label"] == "dog"
        assert (obj["x1"], obj["y1"], obj["x2"], obj["y2"]) == (20, 20, 120, 120)

    def test_requiere_autenticacion(self, client: TestClient) -> None:
        assert client.get(f"/api/events/{uuid4()}").status_code == 401

    def test_evento_inexistente_da_404(self, logged_client: TestClient) -> None:
        assert logged_client.get(f"/api/events/{uuid4()}").status_code == 404


class TestExportacion:
    def test_objects_csv_tiene_una_fila_por_objeto(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, scene_labels=("dog", "car"))

        rows = read_csv(logged_client.get("/api/events/objects.csv").text)

        # 1 trigger + 2 de escena.
        assert len(rows) == 3
        assert {r["source"] for r in rows} == {"trigger", "scene"}
        assert {r["label"] for r in rows} == {"person", "dog", "car"}

    def test_las_columnas_derivadas_estan_normalizadas(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, scene_labels=("dog",))

        rows = read_csv(logged_client.get("/api/events/objects.csv").text)
        perro = next(r for r in rows if r["label"] == "dog")

        # Caja (20,20)-(120,120) sobre un frame de 640x480.
        assert float(perro["box_cx_norm"]) == round(70 / 640, 6)
        assert float(perro["box_cy_norm"]) == round(70 / 480, 6)
        assert float(perro["box_area_ratio"]) == round(100 * 100 / (640 * 480), 6)

    def test_timestamps_en_iso_8601_con_zona(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory)

        [row, *_] = read_csv(logged_client.get("/api/events/objects.csv").text)

        # Debe parsear sin ayuda: es el contrato de "datos limpios".
        parsed = datetime.fromisoformat(row["timestamp_utc"])
        assert parsed.tzinfo is not None

    def test_export_csv_tiene_una_fila_por_evento(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory)
        seed(session_factory)

        rows = read_csv(logged_client.get("/api/events/export.csv").text)

        assert len(rows) == 2

    def test_el_export_respeta_el_filtro_por_clase(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, scene_labels=("dog",))
        seed(session_factory, scene_labels=("car",))

        rows = read_csv(logged_client.get("/api/events/export.csv?label=dog").text)

        assert len(rows) == 1

    def test_no_se_filtra_la_url_de_la_camara(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory)

        body = logged_client.get("/api/events/objects.csv").text

        # La URL puede llevar credenciales: no sale del servidor ni aquí.
        assert "source_url" not in body
        assert "usb" not in body

    def test_exportar_exige_sesion(self, client: TestClient) -> None:
        assert client.get("/api/events/export.csv").status_code == 401
        assert client.get("/api/events/objects.csv").status_code == 401


class TestInyeccionDeFormulas:
    def test_un_nombre_de_camara_con_formula_se_neutraliza(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        # El nombre lo escribe un usuario del panel; sin escapar, Excel
        # ejecutaría la fórmula al abrir el CSV descargado.
        seed(session_factory, camera_name='=WEBSERVICE("http://malo")')

        rows = read_csv(logged_client.get("/api/events/objects.csv").text)

        assert rows[0]["camera_name"].startswith("'=")

    def test_una_zona_con_formula_se_neutraliza(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, camera_zone="+1+1")

        rows = read_csv(logged_client.get("/api/events/export.csv").text)

        assert rows[0]["camera_zone"] == "'+1+1"

    def test_un_nombre_normal_no_se_toca(
        self, logged_client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        seed(session_factory, camera_name="entrada", camera_zone="puerta")

        rows = read_csv(logged_client.get("/api/events/export.csv").text)

        assert rows[0]["camera_name"] == "entrada"
        assert rows[0]["camera_zone"] == "puerta"
