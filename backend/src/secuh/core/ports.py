"""Puertos (interfaces) del dominio.

Cada adaptador de infraestructura implementa una de estas interfaces.
El pipeline (``secuh.core.pipeline``) depende únicamente de lo definido aquí,
lo que permite testearlo con fakes, sin cámara, modelo ni red.

``Frame`` es un arreglo numpy BGR (convención de OpenCV) de forma (alto, ancho, 3).
numpy se considera un tipo de dato, no infraestructura.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterator

import numpy as np
import numpy.typing as npt

from secuh.core.models import Detection, Event, Notification, SceneObject

type Frame = npt.NDArray[np.uint8]


class VideoSource(ABC):
    """Fuente de frames de una cámara (RTSP, MJPEG de IP Webcam, USB)."""

    @abstractmethod
    def frames(self) -> Iterator[Frame]:
        """Itera frames de la fuente. El adaptador es responsable de la
        reconexión; si la fuente se pierde definitivamente, el iterador termina."""

    @abstractmethod
    def close(self) -> None:
        """Libera los recursos de la fuente."""


class MotionDetector(ABC):
    """Pre-filtro barato: decide si un frame amerita correr el detector."""

    @abstractmethod
    def has_motion(self, frame: Frame) -> bool: ...


class PersonDetector(ABC):
    """Detector de personas (YOLO u otro). Solo devuelve la clase persona."""

    @abstractmethod
    def detect(self, frame: Frame) -> list[Detection]:
        """Devuelve las personas detectadas en el frame, sin filtrar por umbral;
        el umbral por cámara lo aplica el pipeline."""


class SceneInspector(ABC):
    """Inventario de todo lo detectable en un frame. Solo observa.

    Se invoca una vez por evento ya confirmado, nunca dentro del bucle de
    vigilancia: no participa en la decisión de disparar (eso es exclusivo de
    ``PersonDetector`` y el pipeline), solo describe la escena en la que
    ocurrió.
    """

    @abstractmethod
    def inspect(self, frame: Frame) -> list[SceneObject]:
        """Devuelve los objetos visibles en el frame, de cualquier clase."""


class Notifier(ABC):
    """Canal de salida de notificaciones (ntfy, Telegram, correo...)."""

    @abstractmethod
    def send(self, notification: Notification) -> None:
        """Envía la notificación. Debe lanzar ``NotificationError`` si falla;
        el pipeline decide qué hacer con el fallo (log + continuar)."""


class EventStore(ABC):
    """Persistencia de eventos (JSONL en modo standalone, BD en modo servidor)."""

    @abstractmethod
    def save(self, event: Event) -> None: ...


class SnapshotStore(ABC):
    """Persistencia de la captura (JPEG) del frame donde se detectó a la persona."""

    @abstractmethod
    def save(self, event: Event, frame: Frame) -> str:
        """Guarda la captura y devuelve su ruta."""


class RawSnapshotStore(ABC):
    """Persistencia de la captura *sin* cajas dibujadas (opcional).

    Es un puerto aparte y no un método más de ``SnapshotStore`` porque es una
    capacidad opcional: guardar el original permite reprocesar el histórico con
    un modelo mejor en el futuro, pero cuesta duplicar el espacio de capturas y
    hay instalaciones donde no compensa.
    """

    @abstractmethod
    def save_raw(self, event: Event, frame: Frame) -> str:
        """Guarda el frame original y devuelve su ruta."""


class ClipRecorder(ABC):
    """Grabación de evidencia alrededor de un evento."""

    @abstractmethod
    def push_frame(self, frame: Frame) -> None:
        """Alimenta el buffer circular de pre-grabación (se llama con cada frame)."""

    @abstractmethod
    def record_event(self, event: Event) -> str:
        """Persiste el clip del evento (pre + post) y devuelve su ruta."""


class Clock(ABC):
    """Fuente de tiempo monotónico, inyectable para testear el cooldown."""

    @abstractmethod
    def now(self) -> float:
        """Segundos monotónicos (equivalente a ``time.monotonic()``)."""


class NotificationError(Exception):
    """Fallo al enviar una notificación por un canal concreto."""
