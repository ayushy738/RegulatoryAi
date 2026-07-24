from __future__ import annotations

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.identity.models import SessionExchangeModel


class SessionExchangesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_source_session(self, source_session_hash: bytes) -> None:
        if self._session.bind is None or self._session.bind.dialect.name != "postgresql":
            return
        lock_key = int.from_bytes(source_session_hash[:8], byteorder="big", signed=True)
        self._session.execute(
            text("select pg_advisory_xact_lock(:lock_key)"),
            {"lock_key": lock_key},
        )

    def get_by_source_session_hash(
        self,
        source_session_hash: bytes,
    ) -> SessionExchangeModel | None:
        statement = select(SessionExchangeModel).where(
            SessionExchangeModel.source_session_hash == source_session_hash
        )
        return self._session.execute(statement).scalar_one_or_none()

    def add(self, exchange: SessionExchangeModel) -> SessionExchangeModel:
        self._session.add(exchange)
        self._session.flush()
        return exchange
