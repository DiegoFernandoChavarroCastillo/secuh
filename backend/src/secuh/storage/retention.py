"""Retención de evidencia: borra clips y capturas más viejos que N días.

Corre en un hilo de fondo (una pasada al arrancar y luego cada hora). Es una
obligación de privacidad, no solo de espacio: la evidencia de vigilancia no
debe acumularse indefinidamente.
"""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

EVIDENCE_PATTERNS = ("clips/**/*.mp4", "snapshots/**/*.jpg")
SWEEP_INTERVAL_SECONDS = 3600.0


def purge_old_evidence(data_dir: Path, retention_days: int) -> int:
    """Borra la evidencia expirada y devuelve cuántos archivos eliminó."""
    cutoff = time.time() - retention_days * 86400
    deleted = 0
    for pattern in EVIDENCE_PATTERNS:
        for path in data_dir.glob(pattern):
            if path.stat().st_mtime < cutoff:
                path.unlink()
                deleted += 1
    if deleted:
        logger.info("Retención: %d archivos de evidencia eliminados", deleted)
    return deleted


class RetentionJob:
    def __init__(self, data_dir: Path, retention_days: int) -> None:
        self._data_dir = data_dir
        self._retention_days = retention_days
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, name="retention", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                purge_old_evidence(self._data_dir, self._retention_days)
            except Exception:
                logger.exception("Fallo en la pasada de retención")
            self._stop.wait(SWEEP_INTERVAL_SECONDS)
