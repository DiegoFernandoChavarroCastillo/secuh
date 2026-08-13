"""Almacenamiento de evidencia: clips, capturas y su retención.

`clips.py` (buffer circular pre-evento), `snapshots.py` y `events.py` (JSONL
del modo standalone) implementan las interfaces ``ClipRecorder``,
``SnapshotStore`` y ``EventStore`` de ``secuh.core.ports``; `retention.py`
borra en segundo plano la evidencia más vieja que ``retention_days``.
"""
