"""Tests de reconciliación del supervisor con fuentes y detector falsos."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import numpy as np
from sqlalchemy.orm import Session, sessionmaker

from secuh.core.models import CameraState, Detection, Notification
from secuh.core.ports import Frame, Notifier, PersonDetector, VideoSource
from secuh.db.models import CameraRow
from secuh.runtime.supervisor import CameraSupervisor
from secuh.settings import ServerSettings


class FakeSource(VideoSource):
    """Emite frames negros a ~20 fps hasta que la cierran."""

    def __init__(self) -> None:
        self._closed = threading.Event()

    def frames(self) -> Iterator[Frame]:
        frame = np.zeros((48, 64, 3), dtype=np.uint8)
        while not self._closed.is_set():
            yield frame
            time.sleep(0.05)

    def close(self) -> None:
        self._closed.set()


class CrashingSource(VideoSource):
    """Simula un fallo fatal del stream (p. ej. OpenCV sin memoria)."""

    def frames(self) -> Iterator[Frame]:
        raise RuntimeError("fallo fatal simulado")

    def close(self) -> None:
        pass


class FakeDetector(PersonDetector):
    def detect(self, frame: Frame) -> list[Detection]:
        return []


class RecordingNotifier(Notifier):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


def add_camera(
    session_factory: sessionmaker[Session], name: str, state: str = "armed"
) -> CameraRow:
    with session_factory() as session:
        row = CameraRow(name=name, source_type="usb", source_url="0", state=state)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row


def make_supervisor(session_factory: sessionmaker[Session], tmp_path: Path) -> CameraSupervisor:
    settings = ServerSettings(
        database_url="sqlite://", data_dir=tmp_path / "data", supervisor_poll_seconds=0.1
    )
    return CameraSupervisor(
        session_factory=session_factory,
        settings=settings,
        notifiers=[],
        detector_factory=FakeDetector,
        source_factory=lambda camera: FakeSource(),
    )


def wait_until(condition: Callable[[], bool], timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return
        time.sleep(0.05)
    raise AssertionError("condición no cumplida a tiempo")


class TestReconciliation:
    def test_camara_armada_arranca_worker_y_reporta_online(
        self, session_factory: sessionmaker[Session], tmp_path: Path
    ) -> None:
        row = add_camera(session_factory, "entrada", state="armed")
        supervisor = make_supervisor(session_factory, tmp_path)
        try:
            supervisor.sync()

            assert supervisor.running_count == 1
            wait_until(lambda: supervisor.is_online(row.id))
        finally:
            supervisor.stop()
        assert supervisor.running_count == 0

    def test_camara_desarmada_no_arranca(
        self, session_factory: sessionmaker[Session], tmp_path: Path
    ) -> None:
        add_camera(session_factory, "entrada", state="disarmed")
        supervisor = make_supervisor(session_factory, tmp_path)
        try:
            supervisor.sync()
            assert supervisor.running_count == 0
        finally:
            supervisor.stop()

    def test_desarmar_detiene_el_worker(
        self, session_factory: sessionmaker[Session], tmp_path: Path
    ) -> None:
        row = add_camera(session_factory, "entrada", state="armed")
        supervisor = make_supervisor(session_factory, tmp_path)
        try:
            supervisor.sync()
            assert supervisor.running_count == 1

            with session_factory() as session:
                db_row = session.get(CameraRow, row.id)
                assert db_row is not None
                db_row.state = CameraState.DISARMED.value
                session.commit()
            supervisor.sync()

            assert supervisor.running_count == 0
        finally:
            supervisor.stop()

    def test_worker_muerto_se_detecta_y_reinicia(
        self, session_factory: sessionmaker[Session], tmp_path: Path
    ) -> None:
        add_camera(session_factory, "entrada", state="armed")
        settings = ServerSettings(
            database_url="sqlite://", data_dir=tmp_path / "data", supervisor_poll_seconds=0.1
        )
        supervisor = CameraSupervisor(
            session_factory=session_factory,
            settings=settings,
            notifiers=[],
            detector_factory=FakeDetector,
            source_factory=lambda camera: CrashingSource(),
        )
        try:
            supervisor.sync()
            [running] = supervisor._running.values()
            wait_until(lambda: not running.thread.is_alive())

            supervisor.sync()  # detecta el hilo muerto y rearranca

            assert supervisor.running_count == 1
            [restarted] = supervisor._running.values()
            assert restarted.worker is not running.worker
        finally:
            supervisor.stop()

    def test_perdida_de_senal_notifica_y_recuperacion_tambien(
        self, session_factory: sessionmaker[Session], tmp_path: Path
    ) -> None:
        add_camera(session_factory, "entrada", state="armed")
        notifier = RecordingNotifier()
        settings = ServerSettings(
            database_url="sqlite://",
            data_dir=tmp_path / "data",
            supervisor_poll_seconds=0.1,
            online_threshold_seconds=0.3,
        )
        source = FakeSource()
        supervisor = CameraSupervisor(
            session_factory=session_factory,
            settings=settings,
            notifiers=[notifier],
            detector_factory=FakeDetector,
            source_factory=lambda camera: source,
        )
        try:
            supervisor.sync()
            [running] = supervisor._running.values()
            wait_until(lambda: running.worker.last_frame_at is not None)
            supervisor.check_signal()  # registra online=True
            assert notifier.sent == []

            source.close()  # se corta la señal
            wait_until(lambda: not supervisor.is_online(running.camera.id), timeout=5)
            supervisor.check_signal()

            assert any("sin señal" in n.message for n in notifier.sent)
        finally:
            supervisor.stop()

    def test_cambio_de_config_reinicia_el_worker(
        self, session_factory: sessionmaker[Session], tmp_path: Path
    ) -> None:
        row = add_camera(session_factory, "entrada", state="armed")
        supervisor = make_supervisor(session_factory, tmp_path)
        try:
            supervisor.sync()
            first_worker = supervisor._running[row.id].worker

            with session_factory() as session:
                db_row = session.get(CameraRow, row.id)
                assert db_row is not None
                db_row.confidence_threshold = 0.9
                session.commit()
            supervisor.sync()

            assert supervisor.running_count == 1
            assert supervisor._running[row.id].worker is not first_worker
            assert supervisor._running[row.id].camera.confidence_threshold == 0.9
        finally:
            supervisor.stop()
