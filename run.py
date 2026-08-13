"""Levanta secuh en local sin Docker: backend (API + detección) y panel juntos.

Uso:
    python run.py

Requiere que ya se haya corrido una vez (ver README):
    cd backend  && uv sync --all-groups
    cd frontend && npm install

Usa SQLite (backend/dev.db) — no hace falta PostgreSQL ni Docker. La primera
vez genera backend/.env con una clave de sesión y una contraseña de admin
aleatorias (se muestran una sola vez; quedan guardadas ahí para las
siguientes ejecuciones). Backend en http://localhost:8000, panel con recarga
en caliente en http://localhost:5173 (proxy a la API, ya configurado).

Ctrl+C apaga ambos procesos.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
ENV_FILE = BACKEND / ".env"


def find_venv_python() -> Path:
    candidates = [BACKEND / ".venv" / "Scripts" / "python.exe", BACKEND / ".venv" / "bin" / "python"]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    sys.exit(
        "No se encontró backend/.venv — corre primero:\n"
        "  cd backend && uv sync --all-groups"
    )


def ensure_env_file() -> None:
    if ENV_FILE.exists():
        return
    admin_password = secrets.token_urlsafe(9)
    secret_key = secrets.token_urlsafe(48)
    ENV_FILE.write_text(
        "\n".join(
            [
                "# Generado por run.py — no compartir ni versionar.",
                "SECUH_DATABASE_URL=sqlite:///./dev.db",
                f"SECUH_SECRET_KEY={secret_key}",
                f"SECUH_ADMIN_PASSWORD={admin_password}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    print("Primera vez: se creó backend/.env con credenciales nuevas.", flush=True)
    print("  Usuario:     admin", flush=True)
    print(f"  Contraseña:  {admin_password}", flush=True)
    print("  (no se vuelven a mostrar; quedan en backend/.env)\n", flush=True)


def ensure_frontend_deps() -> None:
    if not (FRONTEND / "node_modules").exists():
        sys.exit(
            "No se encontró frontend/node_modules — corre primero:\n"
            "  cd frontend && npm install"
        )


def main() -> None:
    python = find_venv_python()
    ensure_env_file()
    ensure_frontend_deps()

    print("Aplicando migraciones...", flush=True)
    subprocess.run([str(python), "-m", "alembic", "upgrade", "head"], cwd=BACKEND, check=True)

    print("Arrancando backend en http://localhost:8000 ...", flush=True)
    backend_proc = subprocess.Popen(
        [
            str(python),
            "-m",
            "uvicorn",
            "--factory",
            "secuh.api.app:create_app",
            "--port",
            "8000",
        ],
        cwd=BACKEND,
    )

    print("Arrancando panel en http://localhost:5173 ...", flush=True)
    npm = "npm.cmd" if os.name == "nt" else "npm"
    frontend_proc = subprocess.Popen([npm, "run", "dev"], cwd=FRONTEND)

    try:
        while True:
            if backend_proc.poll() is not None:
                print("El backend se detuvo; apagando el panel también.")
                break
            if frontend_proc.poll() is not None:
                print("El panel se detuvo; apagando el backend también.")
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print("\nApagando...")
    finally:
        for proc in (backend_proc, frontend_proc):
            if proc.poll() is None:
                proc.terminate()
        for proc in (backend_proc, frontend_proc):
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    main()
