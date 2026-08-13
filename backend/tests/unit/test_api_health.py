"""Tests del endpoint de salud.

El healthcheck de `deploy/docker-compose.yml` consulta `GET /api/health`: si
alguna vez quedara detrás de autenticación, el contenedor se marcaría
`unhealthy` para siempre. Estos tests fijan ese contrato.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealth:
    def test_responde_sin_sesion(self, client: TestClient) -> None:
        response = client.get("/api/health")

        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_informa_cuantos_workers_corren(self, client: TestClient) -> None:
        # El supervisor de los tests (NoopSupervisor) no arranca hilos.
        response = client.get("/api/health")

        assert response.json()["cameras_running"] == 0
