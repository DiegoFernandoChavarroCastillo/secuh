"""Configuración del modo servidor (API + workers), vía variables de entorno.

El modo standalone de Fase 1 (``python -m secuh --config config.yaml``) sigue
usando ``secuh.config``. El servidor toma todo del entorno (12-factor), con
prefijo ``SECUH_`` — pensado para docker compose.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ServerSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SECUH_", env_file=".env", extra="ignore")

    # --- base de datos ---
    database_url: str = "postgresql+psycopg://secuh:secuh@localhost:5432/secuh"

    # --- seguridad ---
    # Clave para firmar los tokens de sesión. OBLIGATORIA en producción:
    # el default solo permite arrancar en desarrollo.
    secret_key: str = "dev-only-insecure-secret"
    session_ttl_hours: int = Field(default=12, ge=1)
    # Usuario admin creado al arrancar si no existe ningún usuario.
    admin_user: str = "admin"
    admin_password: str | None = None
    # Orígenes permitidos para CORS (el dev server de Vite por defecto).
    cors_origins: list[str] = ["http://localhost:5173"]
    # Rate limit de login: intentos fallidos por IP antes de bloquear.
    login_max_attempts: int = Field(default=5, ge=1)
    login_lockout_seconds: float = Field(default=300.0, gt=0)

    # --- detección (compartida por todas las cámaras) ---
    model: str = "yolov8n.pt"
    imgsz: int = Field(default=640, ge=160)
    motion_history: int = Field(default=500, ge=1)
    motion_var_threshold: float = Field(default=16.0, gt=0)
    motion_min_area_ratio: float = Field(default=0.01, gt=0, le=1.0)

    # --- anotación de escena (Fase 7) ---
    # Qué más se veía cuando se detectó a la persona. NO cambia qué dispara un
    # evento ni a quién se notifica: eso sigue siendo solo personas.
    scene_annotation: bool = True
    # Umbral para *registrar* en la base de datos. Bajo a propósito: una fila
    # son unos bytes, y filtrar al analizar es gratis; descartar aquí es
    # perder el dato para siempre.
    scene_min_confidence: float = Field(default=0.25, ge=0.0, le=1.0)
    # Umbral para *dibujar* en la captura. Más alto que el de registro: la foto
    # se mira de un vistazo, la base de datos se consulta con filtros.
    scene_draw_min_confidence: float = Field(default=0.45, ge=0.0, le=1.0)
    # Clases a dibujar. Vacío = todas las que se hayan detectado.
    scene_draw_labels: list[str] = []
    # Guardar también la captura sin cajas, para poder reprocesar el histórico
    # con un modelo mejor más adelante. Duplica el espacio de capturas.
    keep_raw_snapshot: bool = True

    # --- almacenamiento ---
    data_dir: Path = Path("data")
    retention_days: int = Field(default=7, ge=1)
    clip_pre_seconds: float = Field(default=10.0, ge=0)
    clip_post_seconds: float = Field(default=10.0, ge=0)

    # --- notificaciones ---
    # Canal global de respaldo: solo se usa en cámaras que no tienen canales
    # propios asignados en la BD (ver notifications/factory.py).
    ntfy_topic: str | None = None
    console_notifier: bool = True

    # Cada cuántos segundos el supervisor relee las cámaras de la BD.
    supervisor_poll_seconds: float = Field(default=5.0, gt=0)
    # Sin frames durante este tiempo => cámara desconectada (y se alerta).
    online_threshold_seconds: float = Field(default=10.0, gt=0)

    # Carpeta con el build del panel (frontend/dist). Si existe, el backend
    # sirve el panel en "/" — una sola URL para todo el producto.
    frontend_dist: Path | None = None
