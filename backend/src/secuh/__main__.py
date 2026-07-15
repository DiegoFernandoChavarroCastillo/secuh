"""Entry point del MVP: ``python -m secuh [--config config.yaml]``.

Compone los adaptadores según la configuración y corre el worker de la
cámara en el hilo principal hasta Ctrl+C.
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import replace
from pathlib import Path

from secuh.config import AppConfig, load_config
from secuh.core.clock import MonotonicClock
from secuh.core.handler import EventHandler
from secuh.core.models import Camera, CameraState, SourceType
from secuh.core.pipeline import CooldownGate, DetectionPipeline
from secuh.core.ports import Notifier
from secuh.detection.motion import Mog2MotionDetector
from secuh.detection.yolo import YoloPersonDetector
from secuh.logging_setup import setup_logging
from secuh.notifications.console import ConsoleNotifier
from secuh.notifications.ntfy import NtfyNotifier
from secuh.storage.clips import FileClipRecorder
from secuh.storage.events import JsonlEventStore
from secuh.storage.retention import RetentionJob
from secuh.storage.snapshots import FileSnapshotStore
from secuh.video.source import OpenCvVideoSource
from secuh.video.worker import CameraWorker

logger = logging.getLogger(__name__)


def guess_source_type(source: str) -> SourceType:
    if source.isdigit():
        return SourceType.USB
    if source.startswith("rtsp://"):
        return SourceType.RTSP
    return SourceType.IP_WEBCAM


def build_notifiers(config: AppConfig) -> list[Notifier]:
    notifiers: list[Notifier] = []
    if config.notifications.console:
        notifiers.append(ConsoleNotifier())
    if config.notifications.ntfy is not None:
        ntfy = config.notifications.ntfy
        notifiers.append(
            NtfyNotifier(
                topic_url=ntfy.topic_url,
                timeout_seconds=ntfy.timeout_seconds,
                retries=ntfy.retries,
            )
        )
    if not notifiers:
        raise SystemExit("Configura al menos un canal de notificación (console o ntfy).")
    return notifiers


def main() -> None:
    parser = argparse.ArgumentParser(description="secuh — detección de personas")
    parser.add_argument("--config", type=Path, default=Path("config.yaml"))
    args = parser.parse_args()

    setup_logging()
    config = load_config(args.config)

    camera = replace(
        Camera.new(
            name=config.camera.name,
            zone=config.camera.zone,
            source_type=guess_source_type(config.camera.source),
            source_url=config.camera.source,
        ),
        state=CameraState.ARMED,
        confidence_threshold=config.camera.confidence_threshold,
        cooldown_seconds=config.camera.cooldown_seconds,
    )

    detector = YoloPersonDetector(model_path=config.detection.model, imgsz=config.detection.imgsz)
    motion = Mog2MotionDetector(
        history=config.detection.motion_history,
        var_threshold=config.detection.motion_var_threshold,
        min_area_ratio=config.detection.motion_min_area_ratio,
    )
    pipeline = DetectionPipeline(
        camera=camera,
        motion_detector=motion,
        person_detector=detector,
        cooldown=CooldownGate(MonotonicClock()),
    )

    data_dir = config.storage.data_dir
    clip_recorder = FileClipRecorder(
        base_dir=data_dir,
        camera_name=camera.name,
        pre_seconds=config.storage.clip_pre_seconds,
        post_seconds=config.storage.clip_post_seconds,
    )
    handler = EventHandler(
        camera=camera,
        snapshots=FileSnapshotStore(base_dir=data_dir, camera_name=camera.name),
        clips=clip_recorder,
        notifiers=build_notifiers(config),
        events=JsonlEventStore(base_dir=data_dir),
    )

    retention = RetentionJob(data_dir=data_dir, retention_days=config.storage.retention_days)
    retention.start()

    source = OpenCvVideoSource(config.camera.source)
    worker = CameraWorker(
        camera=camera,
        source=source,
        pipeline=pipeline,
        handler=handler,
        clip_recorder=clip_recorder,
        analysis_fps=config.camera.analysis_fps,
    )
    try:
        worker.run()
    except KeyboardInterrupt:
        logger.info("Apagando...")
    finally:
        worker.stop()
        clip_recorder.close()
        retention.stop()


if __name__ == "__main__":
    main()
