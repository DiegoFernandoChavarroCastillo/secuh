"""Seguridad de la API: hash de contraseñas (argon2), tokens de sesión (JWT)
y rate limiting de login.

El panel arma/desarma la vigilancia de un negocio: aunque corra en red local,
la autenticación es obligatoria desde la primera versión (ver plan, Fase 2).
"""

from __future__ import annotations

import threading
import time
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()

SESSION_COOKIE = "secuh_session"
JWT_ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:
        # Hash corrupto o de otro formato: tratar como credencial inválida.
        return False


def create_session_token(username: str, secret_key: str, ttl_hours: int) -> str:
    payload = {
        "sub": username,
        "exp": datetime.now(UTC) + timedelta(hours=ttl_hours),
        "iat": datetime.now(UTC),
    }
    return jwt.encode(payload, secret_key, algorithm=JWT_ALGORITHM)


def decode_session_token(token: str, secret_key: str) -> str | None:
    """Devuelve el username si el token es válido y vigente; None si no."""
    try:
        payload = jwt.decode(token, secret_key, algorithms=[JWT_ALGORITHM])
    except jwt.InvalidTokenError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) else None


class LoginRateLimiter:
    """Bloquea una clave (IP) tras N intentos fallidos, durante un periodo.

    En memoria y por proceso: suficiente para un panel de instalación única.
    """

    def __init__(self, max_attempts: int, lockout_seconds: float) -> None:
        self._max_attempts = max_attempts
        self._lockout_seconds = lockout_seconds
        self._failures: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def is_blocked(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            recent = [t for t in self._failures.get(key, []) if t > now - self._lockout_seconds]
            self._failures[key] = recent
            return len(recent) >= self._max_attempts

    def register_failure(self, key: str) -> None:
        with self._lock:
            self._failures.setdefault(key, []).append(time.monotonic())

    def reset(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)
