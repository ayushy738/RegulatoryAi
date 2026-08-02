from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest

from backend.ask.compatibility_rendering import (
    CompatibilityCitationSnapshot,
    CompatibilityRenderRequest,
)
from backend.ask.legacy_synchronous import (
    LegacySynchronousArtifact,
    LegacySynchronousCancelled,
    LegacySynchronousRunAdapter,
    LegacySynchronousTimeout,
    LegacySynchronousUnavailable,
)
from backend.ask.orchestration.durability import DurableRunStatus
from backend.ask.response_contracts import StructuredResponseEnvelope

FIXTURE_DIR = Path(__file__).parent / "fixtures"
RUN_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
BASE_RESPONSE = StructuredResponseEnvelope.model_validate_json(
    (FIXTURE_DIR / "ask_response_contract.json").read_text(encoding="utf-8")
)


def _artifact() -> LegacySynchronousArtifact:
    citation = CompatibilityCitationSnapshot(
        citation_id="citation-1",
        claim_id="claim-1",
        source_id="source-1",
        ordinal=0,
        verification_status="supported",
        document_id=17,
        title="Regulatory Filing Instrument",
        issuer="Central Regulatory Commission",
        issue_date=date(2026, 6, 15),
        source_url="https://regulator.example/filing",
        chunk_id=101,
        page_number=4,
        section_title="Filing obligation",
        evidence="Every regulated entity must submit the prescribed filing.",
    )
    return LegacySynchronousArtifact(
        run_id=RUN_ID,
        session_id=SESSION_ID,
        user_id=USER_ID,
        response_version=2,
        model="contract-model",
        intent="regulation_lookup",
        event_id=42,
        related_questions=("Which entities are regulated?",),
        compatibility=CompatibilityRenderRequest(
            response=BASE_RESPONSE,
            citation_snapshots=(citation,),
        ),
    )


@dataclass
class _Executor:
    status: DurableRunStatus = DurableRunStatus.COMPLETED
    delay: float = 0
    error: Exception | None = None
    crossed_identity: bool = False
    cancelled: bool = False
    call: dict[str, object] | None = None

    async def execute(self, **kwargs):
        self.call = kwargs
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            if self.error is not None:
                raise self.error
            return SimpleNamespace(
                snapshot=SimpleNamespace(
                    run_id=(UUID(int=9) if self.crossed_identity else RUN_ID),
                    session_id=SESSION_ID,
                    user_id=USER_ID,
                    status=self.status,
                )
            )
        except asyncio.CancelledError:
            self.cancelled = True
            raise


@dataclass
class _Loader:
    artifact: LegacySynchronousArtifact | None
    error: Exception | None = None
    call: dict[str, object] | None = None

    async def load_terminal_artifact(self, **kwargs):
        self.call = kwargs
        if self.error is not None:
            raise self.error
        return self.artifact


def _adapter(
    executor: _Executor,
    loader: _Loader,
) -> LegacySynchronousRunAdapter:
    return LegacySynchronousRunAdapter(
        executor=executor,  # type: ignore[arg-type]
        artifact_loader=loader,
    )


def _await(
    adapter: LegacySynchronousRunAdapter,
    *,
    max_wait: timedelta = timedelta(seconds=1),
    lease_ttl: timedelta = timedelta(milliseconds=500),
):
    return asyncio.run(
        adapter.await_response(
            run_id=RUN_ID,
            session_id=SESSION_ID,
            user_id=USER_ID,
            max_wait=max_wait,
            lease_ttl=lease_ttl,
            max_steps=37,
        )
    )


@pytest.mark.parametrize(
    "status",
    [DurableRunStatus.COMPLETED, DurableRunStatus.PARTIAL],
)
def test_terminal_v2_run_returns_the_exact_legacy_shape(status: DurableRunStatus) -> None:
    executor = _Executor(status=status)
    loader = _Loader(_artifact())

    result = _await(_adapter(executor, loader))

    assert result.model_dump(mode="json") == {
        "reply": (
            "The filing obligation is in force. A related consultation is live, but "
            "official confirmation is pending.\n\nLive Intelligence - not official "
            "regulatory evidence:\n- Regulator announces consultation. | Regulator "
            "Newsroom | published=2026-07-31T10:00:00+05:30 | "
            "retrieved=2026-07-31T10:05:00+05:30 | "
            "https://regulator.example/consultation\n\nGeneral AI Knowledge - "
            "educational context only; not official regulatory evidence.\n\nCoverage "
            "limitations:\n- Official findings: Unsupported card is unavailable in the "
            "legacy view.\n- Live updates: Degraded. Official confirmation is pending."
            "\n\nCitations:\n1. Regulatory Filing Instrument | Central Regulatory "
            "Commission | 2026-06-15 | https://regulator.example/filing | "
            "chunk=101, page=4"
        ),
        "event_id": 42,
        "model": "contract-model",
        "intent": "regulation_lookup",
        "citations": [
            {
                "document_id": 17,
                "title": "Regulatory Filing Instrument",
                "issuer": "Central Regulatory Commission",
                "issue_date": "2026-06-15",
                "source_url": "https://regulator.example/filing",
                "chunk_id": 101,
                "page_number": 4,
                "section_title": "Filing obligation",
                "evidence": "Every regulated entity must submit the prescribed filing.",
            }
        ],
        "related_questions": ["Which entities are regulated?"],
    }
    assert executor.call == {
        "run_id": RUN_ID,
        "session_id": SESSION_ID,
        "user_id": USER_ID,
        "lease_ttl": timedelta(milliseconds=500),
        "max_steps": 37,
    }
    assert loader.call == {
        "run_id": RUN_ID,
        "session_id": SESSION_ID,
        "user_id": USER_ID,
    }


@pytest.mark.parametrize(
    ("status", "error_type", "safe_code"),
    [
        (DurableRunStatus.CANCELLED, LegacySynchronousCancelled, "ASK_CANCELLED"),
        (DurableRunStatus.FAILED, LegacySynchronousUnavailable, "ASK_UNAVAILABLE"),
        (DurableRunStatus.RUNNING, LegacySynchronousUnavailable, "ASK_UNAVAILABLE"),
    ],
)
def test_nonservable_run_states_fail_with_fixed_safe_outcomes(
    status: DurableRunStatus,
    error_type: type[Exception],
    safe_code: str,
) -> None:
    loader = _Loader(_artifact())

    with pytest.raises(error_type) as caught:
        _await(_adapter(_Executor(status=status), loader))

    assert caught.value.safe_code == safe_code  # type: ignore[attr-defined]
    assert loader.call is None


def test_timeout_cancels_the_inflight_wait_and_returns_no_partial_shape() -> None:
    executor = _Executor(delay=0.1)

    with pytest.raises(LegacySynchronousTimeout) as caught:
        _await(
            _adapter(executor, _Loader(_artifact())),
            max_wait=timedelta(milliseconds=5),
            lease_ttl=timedelta(milliseconds=2),
        )

    assert caught.value.safe_code == "ASK_TIMEOUT"
    assert executor.cancelled is True


@pytest.mark.parametrize(
    "failure",
    [
        RuntimeError("provider secret"),
        ValueError("raw database detail"),
        TimeoutError("provider timeout"),
    ],
)
def test_internal_execution_or_loading_failures_are_redacted(failure: Exception) -> None:
    executor = _Executor(error=failure)

    with pytest.raises(LegacySynchronousUnavailable) as caught:
        _await(_adapter(executor, _Loader(_artifact())))

    assert str(failure) not in str(caught.value)
    assert caught.value.safe_code == "ASK_UNAVAILABLE"

    with pytest.raises(LegacySynchronousUnavailable) as caught_loader:
        _await(_adapter(_Executor(), _Loader(_artifact(), error=failure)))
    assert str(failure) not in str(caught_loader.value)


def test_missing_or_crossed_terminal_artifact_fails_closed() -> None:
    with pytest.raises(LegacySynchronousUnavailable):
        _await(_adapter(_Executor(), _Loader(None)))

    crossed = _artifact().model_copy(update={"user_id": UUID(int=8)})
    with pytest.raises(LegacySynchronousUnavailable):
        _await(_adapter(_Executor(), _Loader(crossed)))

    with pytest.raises(LegacySynchronousUnavailable):
        _await(_adapter(_Executor(crossed_identity=True), _Loader(_artifact())))


@pytest.mark.parametrize(
    ("max_wait", "lease_ttl", "message"),
    [
        (timedelta(0), timedelta(seconds=1), "at most 30 seconds"),
        (timedelta(seconds=31), timedelta(seconds=1), "at most 30 seconds"),
        (timedelta(seconds=1), timedelta(0), "within the wait budget"),
        (timedelta(seconds=1), timedelta(seconds=2), "within the wait budget"),
    ],
)
def test_wait_and_worker_budgets_are_bounded(
    max_wait: timedelta,
    lease_ttl: timedelta,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        _await(
            _adapter(_Executor(), _Loader(_artifact())),
            max_wait=max_wait,
            lease_ttl=lease_ttl,
        )


def test_execution_step_budget_is_bounded_before_work_starts() -> None:
    adapter = _adapter(_Executor(), _Loader(_artifact()))

    with pytest.raises(ValueError, match="max steps"):
        asyncio.run(
            adapter.await_response(
                run_id=RUN_ID,
                session_id=SESSION_ID,
                user_id=USER_ID,
                max_wait=timedelta(seconds=1),
                lease_ttl=timedelta(milliseconds=500),
                max_steps=0,
            )
        )


def test_caller_cancellation_is_not_reclassified_as_product_failure() -> None:
    async def cancel() -> None:
        task = asyncio.create_task(
            _adapter(_Executor(delay=1), _Loader(_artifact())).await_response(
                run_id=RUN_ID,
                session_id=SESSION_ID,
                user_id=USER_ID,
                max_wait=timedelta(seconds=2),
                lease_ttl=timedelta(seconds=1),
            )
        )
        await asyncio.sleep(0)
        task.cancel()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel())
