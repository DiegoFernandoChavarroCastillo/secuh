"""EventStore sobre la base de datos, para el modo servidor.

El equivalente del modo standalone es ``secuh.storage.events`` (JSONL).
"""

from __future__ import annotations

from sqlalchemy.orm import Session, sessionmaker

from secuh.core.models import Event
from secuh.core.ports import EventStore
from secuh.db.models import EventRow


class DbEventStore(EventStore):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def save(self, event: Event) -> None:
        with self._session_factory() as session:
            session.add(EventRow.from_domain(event))
            session.commit()
