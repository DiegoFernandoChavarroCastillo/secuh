"""Supervisor: mantiene un worker corriendo por cada cámara armada de la BD.

Cada ``poll_seconds`` relee la tabla de cámaras y reconcilia:

- cámara armada sin worker        -> arranca worker
- cámara desarmada/borrada        -> detiene worker
- configuración de cámara cambió  -> reinicia worker con la nueva config

Así el panel arma/desarma o edita cámaras sin reiniciar el proceso, con una
latencia máxima de ``poll_seconds``.

El modelo YOLO es uno solo por proceso (pesa cientos de MB): se carga
perezosamente al armar la primera cámara y se comparte entre workers
serializando las inferencias con un lock.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

import cv2
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from secuh.core.clock import MonotonicClock
from secuh.core.handler import EventHandler
from secuh.core.models import Camera, CameraState, Detection, Notification
from secuh.core.pipeline import CooldownGate, DetectionPipeline
from secuh.core.ports import Frame, Notifier, PersonDetector, VideoSource
from secuh.db.event_store import DbEventStore
from secuh.db.models import CameraRow
from secuh.detection.motion import Mog2MotionDetector
from secuh.notifications.factory import ChannelConfigError, build_notifier
from secuh.settings import ServerSettings
from secuh.storage.clips import FileClipRecorder
from secuh.storage.snapshots import FileSnapshotStore
from secuh.video.source import OpenCvVideoSource, grab_single_frame
from secuh.video.worker import CameraWorker

logger = logging.getLogger(__name__)


class ThreadSafeDetector(PersonDetector):
    """Serializa las inferencias de un detector compartido entre hilos."""

    def __init__(self, inner: PersonDetector) -> None:
        self._inner = inner
        self._lock = threading.Lock()

    def detect(self, frame: Frame) -> list[Detection]:
        with self._lock:
            return self._inner.detect(frame)


@dataclass
class _Desired:
    """Estado deseado de una cámara según la BD (una fila reconciliable)."""

    camera: Camera
    analysis_fps: float
    channel_specs: list[tuple[str, dict[str, object]]]
    channel_signature: tuple[object, ...]


@dataclass
class _Running:
    camera: Camera
    worker: CameraWorker
    thread: threading.Thread
    recorder: FileClipRecorder
    notifiers: list[Notifier]


def _fingerprint(camera: Camera) -> tuple[object, ...]:
    """Campos cuyo cambio requiere reiniciar el worker."""
    return (
        camera.name,
        camera.source_url,
        camera.source_type,
        camera.confidence_threshold,
        camera.cooldown_seconds,
        camera.schedule,
        camera.mask_polygon,
    )


class CameraSupervisor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        settings: ServerSettings,
        notifiers: list[Notifier],
        detector_factory: Callable[[], PersonDetector] | None = None,
        source_factory: Callable[[Camera], VideoSource] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._settings = settings
        self._notifiers = notifiers
        self._detector_factory = detector_factory or self._default_detector_factory
        self._source_factory = source_factory or (
            lambda camera: OpenCvVideoSource(camera.source_url)
        )
        self._detector: PersonDetector | None = None
        self._running: dict[UUID, _Running] = {}
        self._analysis_fps: dict[UUID, float] = {}
        self._channel_signature: dict[UUID, tuple[object, ...]] = {}
        self._was_online: dict[UUID, bool] = {}
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="supervisor", daemon=True)

    # ------------------------------------------------------------- estado
    @property
    def running_count(self) -> int:
        return len(self._running)

    def is_online(self, camera_id: UUID) -> bool:
        running = self._running.get(camera_id)
        if running is None:
            return False
        last = running.worker.last_frame_at
        return (
            last is not None and (time.monotonic() - last) < self._settings.online_threshold_seconds
        )

    def metrics(self, camera_id: UUID) -> dict[str, float | int] | None:
        running = self._running.get(camera_id)
        return running.worker.metrics if running is not None else None

    def preview_jpeg(self, camera_id: UUID, source_url: str) -> bytes | None:
        """JPEG del frame actual: del worker si corre, o captura puntual."""
        running = self._running.get(camera_id)
        frame = running.worker.last_frame if running is not None else None
        if frame is None:
            frame = grab_single_frame(source_url)
        if frame is None:
            return None
        ok, encoded = cv2.imencode(".jpg", frame)
        return encoded.tobytes() if ok else None

    # ---------------------------------------------------------- ciclo de vida
    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=10)
        for camera_id in list(self._running):
            self._stop_worker(camera_id)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.sync()
                self.check_signal()
            except Exception:
                logger.exception("Fallo reconciliando cámaras")
            self._stop.wait(self._settings.supervisor_poll_seconds)

    def check_signal(self) -> None:
        """Notifica cuando una cámara armada pierde la señal (y cuando vuelve).

        Para un negocio, una cámara caída es en sí un evento de seguridad:
        no basta con reconectar en silencio.
        """
        for camera_id, running in list(self._running.items()):
            online = self.is_online(camera_id)
            was_online = self._was_online.get(camera_id)
            if was_online is True and not online:
                self._notify_signal(
                    running,
                    f"Cámara {running.camera.name} sin señal — revisar conexión",
                    priority="high",
                )
            elif was_online is False and online:
                self._notify_signal(
                    running,
                    f"Cámara {running.camera.name} recuperó la señal",
                    priority="default",
                )
            # None (aún sin primer frame) no dispara alerta: evita falsos
            # avisos durante el arranque.
            if online or was_online is not None:
                self._was_online[camera_id] = online
        for camera_id in list(self._was_online):
            if camera_id not in self._running:
                del self._was_online[camera_id]

    def _notify_signal(self, running: _Running, message: str, priority: str) -> None:
        logger.warning(message, extra={"camera": running.camera.name})
        notification = Notification(
            title="secuh: estado de cámara", message=message, priority=priority
        )
        for notifier in running.notifiers:
            try:
                notifier.send(notification)
            except Exception:
                logger.exception("Fallo notificando estado de cámara")

    # ------------------------------------------------------------- reconcilio
    def sync(self) -> None:
        """Una pasada de reconciliación (pública para poder testearla)."""
        with self._session_factory() as session:
            rows = session.execute(select(CameraRow)).scalars().all()
            desired: dict[UUID, _Desired] = {}
            for row in rows:
                channel_specs = [
                    (channel.type, dict(channel.config))
                    for channel in row.channels
                    if channel.active
                ]
                signature = tuple(
                    (str(channel.id), channel.type, json.dumps(channel.config, sort_keys=True))
                    for channel in sorted(row.channels, key=lambda c: str(c.id))
                    if channel.active
                )
                desired[row.id] = _Desired(
                    camera=row.to_domain(),
                    analysis_fps=row.analysis_fps,
                    channel_specs=channel_specs,
                    channel_signature=signature,
                )

        for camera_id in list(self._running):
            entry = desired.get(camera_id)
            crashed = not self._running[camera_id].thread.is_alive()
            if crashed:
                logger.warning(
                    "Worker muerto detectado; se reiniciará",
                    extra={"camera": self._running[camera_id].camera.name},
                )
            should_stop = (
                crashed
                or entry is None
                or entry.camera.state != CameraState.ARMED
                or _fingerprint(entry.camera) != _fingerprint(self._running[camera_id].camera)
                or entry.analysis_fps != self._analysis_fps.get(camera_id)
                or entry.channel_signature != self._channel_signature.get(camera_id)
            )
            if should_stop:
                self._stop_worker(camera_id)

        for camera_id, entry in desired.items():
            if entry.camera.state == CameraState.ARMED and camera_id not in self._running:
                self._start_worker(entry)

    def _build_camera_notifiers(self, entry: _Desired) -> list[Notifier]:
        """Canales asignados a la cámara; sin canales propios usa los globales."""
        notifiers: list[Notifier] = []
        for channel_type, config in entry.channel_specs:
            try:
                notifiers.append(build_notifier(channel_type, config))
            except ChannelConfigError:
                logger.exception(
                    "Canal mal configurado; se omite",
                    extra={"camera": entry.camera.name, "type": channel_type},
                )
        return notifiers or list(self._notifiers)

    def _start_worker(self, entry: _Desired) -> None:
        camera = entry.camera
        analysis_fps = entry.analysis_fps
        logger.info("Armando cámara", extra={"camera": camera.name})
        detector = self._get_detector()
        settings = self._settings
        notifiers = self._build_camera_notifiers(entry)
        pipeline = DetectionPipeline(
            camera=camera,
            motion_detector=Mog2MotionDetector(
                history=settings.motion_history,
                var_threshold=settings.motion_var_threshold,
                min_area_ratio=settings.motion_min_area_ratio,
                mask_polygon=camera.mask_polygon,
            ),
            person_detector=detector,
            cooldown=CooldownGate(MonotonicClock()),
        )
        recorder = FileClipRecorder(
            base_dir=settings.data_dir,
            camera_name=camera.name,
            pre_seconds=settings.clip_pre_seconds,
            post_seconds=settings.clip_post_seconds,
        )
        handler = EventHandler(
            camera=camera,
            snapshots=FileSnapshotStore(base_dir=settings.data_dir, camera_name=camera.name),
            clips=recorder,
            notifiers=notifiers,
            events=DbEventStore(self._session_factory),
        )
        worker = CameraWorker(
            camera=camera,
            source=self._source_factory(camera),
            pipeline=pipeline,
            handler=handler,
            clip_recorder=recorder,
            analysis_fps=analysis_fps,
        )
        thread = threading.Thread(target=worker.run, name=f"camera-{camera.name}", daemon=True)
        self._running[camera.id] = _Running(
            camera=camera, worker=worker, thread=thread, recorder=recorder, notifiers=notifiers
        )
        self._analysis_fps[camera.id] = analysis_fps
        self._channel_signature[camera.id] = entry.channel_signature
        thread.start()

    def _stop_worker(self, camera_id: UUID) -> None:
        running = self._running.pop(camera_id)
        self._analysis_fps.pop(camera_id, None)
        self._channel_signature.pop(camera_id, None)
        logger.info("Desarmando cámara", extra={"camera": running.camera.name})
        running.worker.stop()
        running.thread.join(timeout=10)
        if running.thread.is_alive():
            logger.warning("El worker no terminó a tiempo", extra={"camera": running.camera.name})
        running.recorder.close()

    # ------------------------------------------------------------- detector
    def _get_detector(self) -> PersonDetector:
        if self._detector is None:
            self._detector = ThreadSafeDetector(self._detector_factory())
        return self._detector

    def _default_detector_factory(self) -> PersonDetector:
        from secuh.detection.yolo import YoloPersonDetector

        return YoloPersonDetector(model_path=self._settings.model, imgsz=self._settings.imgsz)
