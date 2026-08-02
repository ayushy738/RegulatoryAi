from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from backend.ask.compatibility import (
    LegacyCompatibilityError,
    response_version_to_legacy,
    turns_to_legacy_history,
)
from backend.ask.models import (
    AskCitation,
    AskFollowup,
    AskResponseVersion,
    AskRun,
    AskSection,
    AskSource,
    ChatMessage,
    ChatTurn,
)
from backend.ask.persistence import AskPersistenceService
from backend.core.migrations import apply_pending_migrations
from backend.tests.ask_ai_postgres import POSTGRES_MARK, insert_auth_user

CONTRACT_PATH = Path(__file__).parent / "fixtures" / "ask_chat_contract.json"
MIGRATIONS_DIR = Path(__file__).parents[1] / "migrations"
USER_ID = UUID("11111111-1111-4111-8111-111111111111")
SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
RUN_ID = UUID("33333333-3333-4333-8333-333333333333")
SECTION_ID = UUID("44444444-4444-4444-8444-444444444444")
SOURCE_ID = UUID("55555555-5555-4555-8555-555555555555")
CLAIM_ID = UUID("66666666-6666-4666-8666-666666666666")
CITATION_ID = UUID("77777777-7777-4777-8777-777777777777")


@pytest.fixture(scope="module")
def contracts() -> dict[str, Any]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def _message(
    *,
    message_id: int,
    public_id: UUID,
    role: str,
    content: str,
    created_at: datetime,
    event_id: int | None,
    response_version: int | None = None,
) -> ChatMessage:
    return ChatMessage(
        id=message_id,
        public_id=public_id,
        session_id=SESSION_ID,
        user_id=USER_ID,
        event_id=event_id,
        role=role,  # type: ignore[arg-type]
        content=content,
        created_at=created_at,
        status="completed",
        response_version=response_version,
        reply_to_message_id=message_id - 1 if response_version is not None else None,
    )


@contextmanager
def _session_scope(engine: Engine) -> Iterator[Session]:
    database_session = Session(bind=engine)
    try:
        yield database_session
        database_session.commit()
    except Exception:
        database_session.rollback()
        raise
    finally:
        database_session.close()


def _official_version(
    *,
    reply: str,
    event_id: int | None,
    intent: str,
    response_version: int = 1,
    with_evidence: bool = True,
) -> AskResponseVersion:
    created_at = datetime(2026, 7, 27, 10, tzinfo=UTC)
    section = AskSection(
        id=SECTION_ID,
        response_version=response_version,
        ordinal=0,
        section_type="answer",
        status="completed",
        knowledge_mode="official",
        provenance_label="Internal Regulatory Corpus",
        title=None,
        plain_text=reply,
        content={},
        card_schema_version="1",
        model="contract-model",
        policy_version="policy-1",
        prompt_version="prompt-1",
        required_disclosure=None,
        created_at=created_at,
        updated_at=created_at,
    )
    source = AskSource(
        id=SOURCE_ID,
        ordinal=0,
        source_key="document:17:501",
        source_class="official",
        source_type="document_chunk",
        document_id=17,
        document_version_id=None,
        chunk_id=501,
        graph_reference=None,
        title_snapshot="Electricity Rules",
        url_snapshot="https://example.test/rules",
        issuer_snapshot="Ministry of Power",
        publisher_snapshot=None,
        jurisdiction_snapshot="central",
        published_at=datetime(2026, 7, 1, tzinfo=UTC),
        retrieved_at=created_at,
        evidence_snapshot="The rules apply to licensed distribution entities.",
        locator_snapshot="page 7, Applicability",
        content_hash="sha256:contract",
        metadata={"page_number": 7, "section_title": "Applicability"},
        created_at=created_at,
    )
    citation = AskCitation(
        id=CITATION_ID,
        claim_id=CLAIM_ID,
        source_id=SOURCE_ID,
        ordinal=0,
        claim_knowledge_mode="official",
        source_class="official",
        citation_kind="official_citation",
        marker="[1]",
        evidence_snapshot="The rules apply to licensed distribution entities.",
        locator_snapshot="page 7",
        support_score=0.99,
        verification_status="verified",
        verifier_model="verifier",
        verifier_policy_version="verify-1",
        created_at=created_at,
    )
    followup = AskFollowup(
        id=UUID("88888888-8888-4888-8888-888888888888"),
        ordinal=0,
        label="Licensed entities",
        question=(
            "Which entities are licensed?"
            if with_evidence
            else "Try a named regulation"
        ),
        action_type="ask",
        payload={},
        created_at=created_at,
    )
    run = AskRun(
        id=RUN_ID,
        status="completed",
        knowledge_mode_summary={"official": with_evidence},
        model="contract-model",
        policy_version="policy-1",
        prompt_version="prompt-1",
        general_ai_disclosure=None,
        safe_error_code=None,
        safe_error_message=None,
        started_at=created_at,
        completed_at=created_at,
        created_at=created_at,
        updated_at=created_at,
        sections=(section,) if with_evidence else (),
        sources=(source,) if with_evidence else (),
        claims=(),
        citations=(citation,) if with_evidence else (),
        followups=(followup,),
        response_version=response_version,
        decision_record={"intent": {"primary": intent}},
    )
    assistant = _message(
        message_id=12 + response_version,
        public_id=UUID(f"99999999-9999-4999-8999-{response_version:012d}"),
        role="assistant",
        content=reply,
        created_at=created_at,
        event_id=event_id,
        response_version=response_version,
    )
    return AskResponseVersion(
        response_version=response_version,
        assistant_message=assistant,
        run=run,
        feedback=None,
    )


def test_grounded_response_matches_legacy_success_golden(
    contracts: dict[str, Any],
) -> None:
    version = _official_version(
        reply=contracts["success"]["reply"],
        event_id=42,
        intent="regulation_lookup",
    )

    result = response_version_to_legacy(version)

    assert result.model_dump(mode="json") == contracts["success"]


def test_no_evidence_response_matches_legacy_fallback_golden(
    contracts: dict[str, Any],
) -> None:
    version = _official_version(
        reply=contracts["no_citations"]["reply"],
        event_id=None,
        intent="general_question",
        with_evidence=False,
    )

    result = response_version_to_legacy(version)

    assert result.model_dump(mode="json") == contracts["no_citations"]


def test_adapter_uses_the_explicit_response_version_without_rewriting_history() -> None:
    first = _official_version(
        reply="Original answer",
        event_id=42,
        intent="regulation_lookup",
        response_version=1,
        with_evidence=False,
    )
    second = _official_version(
        reply="Regenerated answer",
        event_id=42,
        intent="regulation_lookup",
        response_version=2,
        with_evidence=False,
    )

    assert response_version_to_legacy(first).reply == "Original answer"
    assert response_version_to_legacy(second).reply == "Regenerated answer"

    mismatched_message = replace(
        second,
        assistant_message=replace(second.assistant_message, response_version=1),
    )
    with pytest.raises(LegacyCompatibilityError, match="versions do not match"):
        response_version_to_legacy(mismatched_message)


def test_history_mapping_matches_descending_legacy_shape_and_event_scope(
    contracts: dict[str, Any],
) -> None:
    user = _message(
        message_id=8,
        public_id=UUID("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        role="user",
        content="Earlier question",
        created_at=datetime(2026, 7, 26, 10, 4, tzinfo=UTC),
        event_id=77,
    )
    assistant = _message(
        message_id=9,
        public_id=UUID("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"),
        role="assistant",
        content="Newest answer",
        created_at=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
        event_id=77,
        response_version=1,
    )
    ignored = _message(
        message_id=10,
        public_id=UUID("cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        role="assistant",
        content="Global answer",
        created_at=datetime(2026, 7, 26, 10, 6, tzinfo=UTC),
        event_id=None,
    )
    turns = (
        ChatTurn(
            anchor_id=8,
            anchor_created_at=user.created_at,
            user_message=user,
            assistant_message=assistant,
            run=None,
        ),
        ChatTurn(
            anchor_id=10,
            anchor_created_at=ignored.created_at,
            user_message=None,
            assistant_message=ignored,
            run=None,
        ),
    )

    result = turns_to_legacy_history(turns, event_id=77)
    json_result = [
        {
            **item,
            "created_at": item["created_at"].isoformat(),
        }
        for item in result
    ]

    assert json_result == contracts["history"]
    assert turns_to_legacy_history(turns, event_id=None)[0]["id"] == 10


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda version: replace(
                version,
                assistant_message=replace(version.assistant_message, status="pending"),
            ),
            "completed assistant",
        ),
        (
            lambda version: replace(version, run=replace(version.run, status="partial")),
            "completed Ask run",
        ),
        (
            lambda version: replace(version, run=replace(version.run, model=None)),
            "requires a model",
        ),
        (
            lambda version: replace(
                version,
                run=replace(version.run, decision_record={}),
            ),
            "persisted intent",
        ),
    ],
)
def test_adapter_rejects_incomplete_or_unrepresentable_core_state(
    mutation: Any,
    message: str,
) -> None:
    version = _official_version(
        reply="Grounded answer",
        event_id=42,
        intent="regulation_lookup",
        with_evidence=False,
    )

    with pytest.raises(LegacyCompatibilityError, match=message):
        response_version_to_legacy(mutation(version))


def test_adapter_rejects_provenance_and_citation_states_legacy_cannot_label() -> None:
    version = _official_version(
        reply="Grounded answer",
        event_id=42,
        intent="regulation_lookup",
    )
    general_section = replace(
        version.run.sections[0],
        knowledge_mode="general",
        provenance_label="General AI Knowledge",
        required_disclosure="General background only.",
    )
    with pytest.raises(LegacyCompatibilityError, match="General AI or live"):
        response_version_to_legacy(
            replace(version, run=replace(version.run, sections=(general_section,)))
        )

    missing_source_citation = replace(
        version.run.citations[0],
        source_id=UUID("dddddddd-dddd-4ddd-8ddd-dddddddddddd"),
    )
    with pytest.raises(LegacyCompatibilityError, match="missing its persisted source"):
        response_version_to_legacy(
            replace(
                version,
                run=replace(version.run, citations=(missing_source_citation,)),
            )
        )


def test_history_mapping_rejects_duplicate_identity_and_invalid_limit() -> None:
    message = _message(
        message_id=9,
        public_id=UUID("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee"),
        role="assistant",
        content="Answer",
        created_at=datetime(2026, 7, 26, 10, 5, tzinfo=UTC),
        event_id=77,
    )
    duplicate = ChatTurn(
        anchor_id=9,
        anchor_created_at=message.created_at,
        user_message=message,
        assistant_message=message,
        run=None,
    )

    with pytest.raises(LegacyCompatibilityError, match="IDs must be unique"):
        turns_to_legacy_history((duplicate,), event_id=77)
    with pytest.raises(ValueError, match="limit must be positive"):
        turns_to_legacy_history((), event_id=77, limit=0)


@POSTGRES_MARK
def test_repository_restored_version_maps_to_legacy_no_evidence_golden(
    postgres_engine: Engine,
    contracts: dict[str, Any],
) -> None:
    apply_pending_migrations(postgres_engine, MIGRATIONS_DIR, through="0028")
    owner_id = uuid4()
    session_id = uuid4()
    assistant_public_id = uuid4()
    with postgres_engine.begin() as connection:
        insert_auth_user(connection, owner_id)
        connection.execute(
            text(
                """
                insert into public.chat_sessions (id, user_id, title)
                values (:session_id, :user_id, 'Compatibility workspace')
                """
            ),
            {"session_id": session_id, "user_id": owner_id},
        )
        user_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content, status
                )
                values (
                  :public_id, :session_id, :user_id, 'user',
                  'Unknown topic', 'completed'
                )
                returning id
                """
            ),
            {
                "public_id": uuid4(),
                "session_id": session_id,
                "user_id": owner_id,
            },
        ).scalar_one()
        assistant_message_id = connection.execute(
            text(
                """
                insert into public.chat_messages (
                  public_id, session_id, user_id, role, content, status,
                  response_version, reply_to_message_id
                )
                values (
                  :public_id, :session_id, :user_id, 'assistant', :content,
                  'completed', 1, :user_message_id
                )
                returning id
                """
            ),
            {
                "public_id": assistant_public_id,
                "session_id": session_id,
                "user_id": owner_id,
                "content": contracts["no_citations"]["reply"],
                "user_message_id": user_message_id,
            },
        ).scalar_one()
        run_id = connection.execute(
            text(
                """
                insert into public.ask_runs (
                  session_id, user_id, user_message_id, assistant_message_id,
                  response_version, status, decision_record, model
                )
                values (
                  :session_id, :user_id, :user_message_id, :assistant_message_id,
                  1, 'completed',
                  '{"intent":{"primary":"general_question"}}'::jsonb,
                  'contract-model'
                )
                returning id
                """
            ),
            {
                "session_id": session_id,
                "user_id": owner_id,
                "user_message_id": user_message_id,
                "assistant_message_id": assistant_message_id,
            },
        ).scalar_one()
        connection.execute(
            text(
                """
                insert into public.ask_followups (
                  run_id, session_id, user_id, ordinal, label, question
                )
                values (
                  :run_id, :session_id, :user_id, 0,
                  'Try a regulation', 'Try a named regulation'
                )
                """
            ),
            {"run_id": run_id, "session_id": session_id, "user_id": owner_id},
        )

    service = AskPersistenceService(lambda: _session_scope(postgres_engine))
    restored = service.get_response_version(
        assistant_message_public_id=assistant_public_id,
        user_id=owner_id,
    )

    assert restored is not None
    assert response_version_to_legacy(restored).model_dump(mode="json") == contracts[
        "no_citations"
    ]
