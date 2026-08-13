"""Tests de autenticación de la API."""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from secuh.api.security import hash_password
from secuh.db.models import UserRow


def create_user(
    session_factory: sessionmaker[Session], username: str = "diego", password: str = "clave-1"
) -> None:
    with session_factory() as session:
        session.add(UserRow(username=username, password_hash=hash_password(password)))
        session.commit()


class TestLogin:
    def test_login_correcto_devuelve_cookie_de_sesion(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        create_user(session_factory)

        response = client.post("/api/auth/login", json={"username": "diego", "password": "clave-1"})

        assert response.status_code == 200
        assert response.json() == {"username": "diego"}
        assert "secuh_session" in response.cookies

    def test_password_incorrecta_da_401_sin_revelar_si_el_usuario_existe(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        create_user(session_factory)

        wrong_pass = client.post("/api/auth/login", json={"username": "diego", "password": "mala"})
        no_user = client.post("/api/auth/login", json={"username": "nadie", "password": "mala"})

        assert wrong_pass.status_code == no_user.status_code == 401
        assert wrong_pass.json() == no_user.json()

    def test_bloqueo_tras_intentos_fallidos(
        self, client: TestClient, session_factory: sessionmaker[Session]
    ) -> None:
        create_user(session_factory)
        for _ in range(5):
            client.post("/api/auth/login", json={"username": "diego", "password": "mala"})

        blocked = client.post("/api/auth/login", json={"username": "diego", "password": "clave-1"})

        assert blocked.status_code == 429


class TestSession:
    def test_me_requiere_sesion(self, client: TestClient) -> None:
        assert client.get("/api/auth/me").status_code == 401

    def test_me_con_sesion(self, logged_client: TestClient) -> None:
        response = logged_client.get("/api/auth/me")
        assert response.status_code == 200
        assert response.json()["username"] == "diego"

    def test_logout_invalida_la_cookie(self, logged_client: TestClient) -> None:
        logged_client.post("/api/auth/logout")
        assert logged_client.get("/api/auth/me").status_code == 401

    def test_cookie_manipulada_es_rechazada(self, logged_client: TestClient) -> None:
        logged_client.cookies.set("secuh_session", "token-falso")
        assert logged_client.get("/api/auth/me").status_code == 401


class TestBootstrapAdmin:
    def test_admin_inicial_puede_loguearse(self, client: TestClient) -> None:
        # create_app corre bootstrap_admin en el lifespan con admin_password
        # de los settings de test.
        response = client.post(
            "/api/auth/login", json={"username": "admin", "password": "admin-password-test"}
        )
        assert response.status_code == 200
