"""Estado en tiempo real del sistema vía Server-Sent Events.

El panel se suscribe a ``/api/stream`` y recibe cada ~2 s el estado de las
cámaras y el id del último evento — sin refrescar la página ni hacer polling
HTTP desde el navegador.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import anyio
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from secuh.api.deps import get_current_user
from secuh.db.models import CameraRow, EventRow
from secuh.runtime.supervisor import CameraSupervisor

router = APIRouter(tags=["stream"], dependencies=[Depends(get_current_user)])

PUSH_INTERVAL_SECONDS = 2.0


def build_status(
    session_factory: sessionmaker[Session], supervisor: CameraSupervisor
) -> dict[str, Any]:
    with session_factory() as session:
        cameras = session.execute(select(CameraRow)).scalars().all()
        latest = session.execute(
            select(EventRow.id).order_by(EventRow.timestamp.desc()).limit(1)
        ).scalar_one_or_none()
        return {
            "type": "status",
            "cameras": [
                {
                    "id": str(row.id),
                    "state": row.state,
                    "online": supervisor.is_online(row.id),
                }
                for row in cameras
            ],
            "latest_event_id": str(latest) if latest else None,
        }


@router.get("/stream")
async def stream(request: Request) -> StreamingResponse:
    session_factory = request.app.state.session_factory
    supervisor = request.app.state.supervisor

    async def generate() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            payload = await anyio.to_thread.run_sync(build_status, session_factory, supervisor)
            yield f"data: {json.dumps(payload)}\n\n"
            await asyncio.sleep(PUSH_INTERVAL_SECONDS)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
