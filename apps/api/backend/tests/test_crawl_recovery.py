"""Crawl abandonment reclaim and incomplete-document downstream retry."""

from __future__ import annotations

import re
from typing import Any

import pytest
from sqlalchemy import text as sa_text
from sqlalchemy.dialects import postgresql

from backend.pipeline import crawl_recovery
from backend.pipeline.crawl_recovery import (
    ABANDONED_ERROR_CODE,
    reclaim_stale_crawl_runs,
    retry_incomplete_document_downstream,
)


class _Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None, scalar: Any = None):
        self._rows = rows or []
        self._scalar = scalar

    def mappings(self) -> "_Result":
        return self

    def first(self) -> dict[str, Any] | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)

    def scalar(self) -> Any:
        return self._scalar


def test_reclaim_stale_runs_updates_only_aged_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            sql = str(statement)
            captured["sql"] = sql
            captured["params"] = params
            assert "status = cast('running' as run_status_t)" in sql
            assert "finished_at is null" in sql
            assert "for update skip locked" in sql
            assert params is not None
            assert params["stale_seconds"] == 120
            assert params["error_code"] == ABANDONED_ERROR_CODE
            return _Result(
                [
                    {
                        "id": 58,
                        "docs_found": 2,
                        "new_events": 1,
                        "started_at": "t0",
                        "finished_at": "t1",
                    }
                ]
            )

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(crawl_recovery, "session_scope", lambda: Session())
    result = reclaim_stale_crawl_runs(stale_seconds=120)
    assert result["reclaimed"] == 1
    assert result["runs"][0]["id"] == 58
    assert (
        "started_at < (now() - (cast(:stale_seconds as int) * interval '1 second'))"
        in captured["sql"]
    )


def test_reclaim_force_requires_run_id() -> None:
    with pytest.raises(ValueError, match="force reclaim requires"):
        reclaim_stale_crawl_runs(force=True)


def test_reclaim_force_skips_age_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            captured["sql"] = str(statement)
            captured["params"] = params
            return _Result([{"id": 58, "docs_found": 2, "new_events": 1,
                             "started_at": "t0", "finished_at": "t1"}])

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(crawl_recovery, "session_scope", lambda: Session())
    result = reclaim_stale_crawl_runs(run_id=58, force=True)
    assert result["reclaimed"] == 1
    assert result["force"] is True
    assert "started_at <" not in captured["sql"]
    assert "id = cast(:run_id as bigint)" in captured["sql"]


@pytest.mark.parametrize("force", [True, False])
def test_reclaim_binds_every_parameter_with_explicit_cast(
    monkeypatch: pytest.MonkeyPatch, force: bool
) -> None:
    """Regression: PostgreSQL raised IndeterminateDatatype for run_id=58.

    Bound parameters reach ``jsonb_build_object``, a ``variadic "any"`` function
    that gives PostgreSQL no context to infer types, so every parameter must
    carry an explicit cast matching its column type.
    """

    captured: dict[str, Any] = {}

    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            captured["sql"] = str(statement)
            captured["params"] = params
            return _Result([{"id": 58, "docs_found": 2, "new_events": 1,
                             "started_at": "t0", "finished_at": "t1"}])

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(crawl_recovery, "session_scope", lambda: Session())
    result = reclaim_stale_crawl_runs(run_id=58, stale_seconds=7200, force=force)
    assert result["reclaimed"] == 1

    sql = captured["sql"]
    assert captured["params"] == {
        "stale_seconds": 7200,
        "error_code": ABANDONED_ERROR_CODE,
        "run_id": 58,
    }
    assert isinstance(captured["params"]["run_id"], int)

    expected_casts = {
        "stale_seconds": "int",
        "error_code": "text",
        "run_id": "bigint",  # crawl_runs.id is bigint
    }
    referenced = {match.group(1) for match in re.finditer(r"(?<!:):([A-Za-z_]\w*)", sql)}
    assert referenced == {"stale_seconds", "error_code", "run_id"}
    for name, sql_type in expected_casts.items():
        occurrences = len(re.findall(rf"(?<!:):{name}\b", sql))
        wrapped = len(re.findall(rf"cast\(:{name} as {sql_type}\)", sql))
        assert occurrences == wrapped, f":{name} is bound without cast(... as {sql_type})"

    # `:name::type` is not an option: SQLAlchemy's text() refuses to bind a
    # parameter followed by ':', so the colon would reach PostgreSQL verbatim.
    compiled = str(sa_text(sql).compile(dialect=postgresql.dialect(paramstyle="pyformat")))
    for name in expected_casts:
        assert f"%({name})s" in compiled
    assert not re.search(r"(?<!:):[A-Za-z_]", compiled), "unbound parameter reached the driver"

    assert "for update skip locked" in sql
    assert sql.count("update crawl_runs cr") == 1


def test_reclaim_is_idempotent_when_no_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            return _Result([])

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(crawl_recovery, "session_scope", lambda: Session())
    first = reclaim_stale_crawl_runs(stale_seconds=120)
    second = reclaim_stale_crawl_runs(stale_seconds=120)
    assert first["reclaimed"] == 0
    assert second["reclaimed"] == 0


def test_active_run_younger_than_threshold_not_selected_in_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fresh running rows keep the age predicate; reclaim returns empty."""

    class Session:
        def execute(self, statement: Any, params: dict[str, Any] | None = None) -> _Result:
            assert params is not None
            assert params["stale_seconds"] == 7200
            return _Result([])

        def __enter__(self) -> "Session":
            return self

        def __exit__(self, *args: object) -> None:
            return None

    monkeypatch.setattr(crawl_recovery, "session_scope", lambda: Session())
    assert reclaim_stale_crawl_runs()["reclaimed"] == 0


def test_retry_incomplete_document_skips_duplicate_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FakeState:
        document_id: int = 274
        version_id: int = 274
        create_events: bool = True

    state = FakeState()
    seen: dict[str, Any] = {}

    def fake_downstream(arg: Any) -> int | None:
        seen["create_events"] = arg.create_events
        return None

    monkeypatch.setattr(crawl_recovery, "_load_durable_state_for_retry", lambda _id: state)
    monkeypatch.setattr(crawl_recovery, "_event_count_for_document", lambda _id: 1)
    monkeypatch.setattr(crawl_recovery, "_process_document_downstream", fake_downstream)
    monkeypatch.setattr(crawl_recovery, "_graph_status", lambda _id: "COMPLETED")
    monkeypatch.setattr(
        crawl_recovery,
        "_rag_snapshot",
        lambda _id: {"job_status": "PENDING", "rag_status": "PENDING"},
    )

    result = retry_incomplete_document_downstream(274)
    assert result["status"] == "COMPLETED"
    assert result["events_already_present"] == 1
    assert seen["create_events"] is False


def test_retry_incomplete_document_creates_events_when_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class FakeState:
        document_id: int = 274
        version_id: int = 274
        create_events: bool = True

    state = FakeState()

    def fake_downstream(arg: Any) -> int:
        assert arg.create_events is True
        return 999

    monkeypatch.setattr(crawl_recovery, "_load_durable_state_for_retry", lambda _id: state)
    monkeypatch.setattr(crawl_recovery, "_event_count_for_document", lambda _id: 0)
    monkeypatch.setattr(crawl_recovery, "_process_document_downstream", fake_downstream)
    monkeypatch.setattr(crawl_recovery, "_graph_status", lambda _id: "COMPLETED")
    monkeypatch.setattr(
        crawl_recovery,
        "_rag_snapshot",
        lambda _id: {"job_status": "PENDING", "rag_status": "PENDING"},
    )

    result = retry_incomplete_document_downstream(274)
    assert result["event_id"] == 999
    assert result["events_already_present"] == 0


def test_retry_missing_document_returns_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(crawl_recovery, "_load_durable_state_for_retry", lambda _id: None)
    result = retry_incomplete_document_downstream(999)
    assert result["status"] == "FAILED"
    assert "could not be loaded" in (result["error"] or "")
