"""Tests de los adaptadores de almacenamiento (JSONL, retención, clips)."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import numpy as np

from secuh.core.models import BoundingBox, Camera, Detection, Event, SourceType
from secuh.core.ports import Frame
from secuh.storage.clips import FileClipRecorder
from secuh.storage.events import JsonlEventStore
from secuh.storage.retention import purge_old_evidence


def make_event() -> Event:
    camera = Camera.new("entrada", "puerta", SourceType.USB, "0")
    return Event.new(
        camera_id=camera.id,
        detections=(Detection(box=BoundingBox(1, 2, 3, 4), confidence=0.9),),
    )


def make_frame(value: int = 0) -> Frame:
    return np.full((48, 64, 3), value, dtype=np.uint8)


class TestJsonlEventStore:
    def test_guarda_y_serializa_el_evento(self, tmp_path: Path) -> None:
        store = JsonlEventStore(base_dir=tmp_path)
        event = make_event()

        store.save(event)

        [line] = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        record = json.loads(line)
        assert record["id"] == str(event.id)
        assert record["camera_id"] == str(event.camera_id)
        assert record["detections"][0]["confidence"] == 0.9

    def test_agrega_sin_sobrescribir(self, tmp_path: Path) -> None:
        store = JsonlEventStore(base_dir=tmp_path)
        store.save(make_event())
        store.save(make_event())

        lines = (tmp_path / "events.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2


class TestRetention:
    def test_borra_solo_evidencia_expirada(self, tmp_path: Path) -> None:
        old_clip = tmp_path / "clips" / "cam" / "viejo.mp4"
        new_clip = tmp_path / "clips" / "cam" / "nuevo.mp4"
        old_snap = tmp_path / "snapshots" / "cam" / "viejo.jpg"
        for f in (old_clip, new_clip, old_snap):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(b"x")
        expired = time.time() - 8 * 86400
        os.utime(old_clip, (expired, expired))
        os.utime(old_snap, (expired, expired))

        deleted = purge_old_evidence(tmp_path, retention_days=7)

        assert deleted == 2
        assert not old_clip.exists()
        assert not old_snap.exists()
        assert new_clip.exists()

    def test_no_toca_otros_archivos(self, tmp_path: Path) -> None:
        events = tmp_path / "events.jsonl"
        events.write_text("{}", encoding="utf-8")
        expired = time.time() - 30 * 86400
        os.utime(events, (expired, expired))

        assert purge_old_evidence(tmp_path, retention_days=7) == 0
        assert events.exists()


class TestFileClipRecorder:
    def test_graba_pre_y_post_y_cierra_el_archivo(self, tmp_path: Path) -> None:
        recorder = FileClipRecorder(
            base_dir=tmp_path, camera_name="cam", pre_seconds=5.0, post_seconds=0.0
        )
        for i in range(10):
            recorder.push_frame(make_frame(i * 20))

        path = Path(recorder.record_event(make_event()))
        # post_seconds=0: el siguiente frame finaliza la grabación.
        recorder.push_frame(make_frame(255))

        assert path.exists()
        assert path.stat().st_size > 0
        assert path.suffix == ".mp4"

    def test_evento_durante_grabacion_activa_extiende_el_mismo_clip(self, tmp_path: Path) -> None:
        recorder = FileClipRecorder(
            base_dir=tmp_path, camera_name="cam", pre_seconds=5.0, post_seconds=60.0
        )
        recorder.push_frame(make_frame())

        first = recorder.record_event(make_event())
        recorder.push_frame(make_frame())
        second = recorder.record_event(make_event())

        assert first == second
        recorder.close()
        assert Path(first).exists()
