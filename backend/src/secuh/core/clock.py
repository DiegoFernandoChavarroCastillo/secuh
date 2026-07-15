"""Implementación real del puerto ``Clock``."""

from __future__ import annotations

import time

from secuh.core.ports import Clock


class MonotonicClock(Clock):
    def now(self) -> float:
        return time.monotonic()
