from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.ask.orchestration import (
    CONTEXT_SELECTION_POLICY_VERSION,
    ContextMessageRole,
    ContextTurnStatus,
    ConversationContextCandidate,
    ConversationContextRequest,
    ConversationContextSelection,
    conversation_context_json,
    select_conversation_context,
)

SESSION_ID = UUID("11111111-1111-4111-8111-111111111111")
OTHER_SESSION_ID = UUID("22222222-2222-4222-8222-222222222222")
USER_ID = UUID("33333333-3333-4333-8333-333333333333")
OTHER_USER_ID = UUID("44444444-4444-4444-8444-444444444444")
STARTED_AT = datetime(2026, 7, 27, 8, 0, tzinfo=UTC)


def _candidate(
    index: int,
    *,
    session_id: UUID = SESSION_ID,
    user_id: UUID = USER_ID,
    keys: tuple[str, ...] = ("entity:dsm",),
    status: ContextTurnStatus = ContextTurnStatus.COMPLETED,
    inheritance_eligible: bool = True,
) -> ConversationContextCandidate:
    user_created_at = STARTED_AT + timedelta(minutes=index)
    return ConversationContextCandidate(
        turn_id=UUID(int=index),
        session_id=session_id,
        user_id=user_id,
        anchor_id=index,
        user_created_at=user_created_at,
        assistant_created_at=user_created_at + timedelta(seconds=10),
        user_content=f"Question {index}",
        assistant_content=f"Answer {index}",
        status=status,
        context_keys=keys,
        inheritance_eligible=inheritance_eligible,
    )


def _request(
    candidates: tuple[ConversationContextCandidate, ...],
    **overrides,
) -> ConversationContextRequest:
    values = {
        "session_id": SESSION_ID,
        "user_id": USER_ID,
        "candidates": candidates,
        "relevance_keys": ("entity:dsm",),
    }
    values.update(overrides)
    return ConversationContextRequest.model_validate(values)


def test_selects_newest_relevant_turns_then_serializes_chronologically() -> None:
    candidates = tuple(_candidate(index) for index in range(1, 11))

    result = select_conversation_context(
        _request(tuple(reversed(candidates)), max_turns=3)
    )

    assert result.selected_turn_ids == tuple(
        UUID(int=index) for index in (8, 9, 10)
    )
    assert [message.content for message in result.messages] == [
        "Question 8",
        "Answer 8",
        "Question 9",
        "Answer 9",
        "Question 10",
        "Answer 10",
    ]
    assert result.truncated_relevant_count == 7
    assert result.excluded_irrelevant_count == 0


def test_filters_other_sessions_users_and_noncompleted_turns() -> None:
    candidates = (
        _candidate(1),
        _candidate(2, session_id=OTHER_SESSION_ID),
        _candidate(3, user_id=OTHER_USER_ID),
        _candidate(4, status=ContextTurnStatus.INCOMPLETE),
        _candidate(5, status=ContextTurnStatus.FAILED),
        _candidate(6, status=ContextTurnStatus.CANCELLED),
    )

    result = select_conversation_context(_request(candidates))

    assert result.selected_turn_ids == (UUID(int=1),)
    assert result.excluded_wrong_owner_or_session_count == 2
    assert result.excluded_noncompleted_count == 3


def test_explicit_new_scope_excludes_newer_unrelated_turns() -> None:
    candidates = (
        _candidate(1, keys=("entity:abt",)),
        _candidate(2, keys=("entity:dsm",)),
        _candidate(3, keys=("entity:green-hydrogen",)),
    )

    result = select_conversation_context(
        _request(candidates, relevance_keys=("ENTITY:ABT",))
    )

    assert result.selected_turn_ids == (UUID(int=1),)
    assert result.excluded_irrelevant_count == 2


def test_immediate_follow_up_retains_latest_completed_turn_without_keys() -> None:
    candidates = (
        _candidate(1, keys=("entity:abt",)),
        _candidate(2, keys=("entity:dsm",)),
    )

    result = select_conversation_context(
        _request(
            candidates,
            relevance_keys=(),
            requires_immediate_context=True,
        )
    )

    assert result.selected_turn_ids == (UUID(int=2),)
    assert [message.role for message in result.messages] == [
        ContextMessageRole.USER,
        ContextMessageRole.ASSISTANT,
    ]


def test_immediate_follow_up_and_relevance_share_one_bounded_selection() -> None:
    candidates = (
        _candidate(1, keys=("entity:abt",)),
        _candidate(2, keys=("entity:abt",)),
        _candidate(3, keys=("entity:dsm",)),
    )

    result = select_conversation_context(
        _request(
            candidates,
            relevance_keys=("entity:abt",),
            requires_immediate_context=True,
            max_turns=2,
        )
    )

    assert result.selected_turn_ids == (UUID(int=2), UUID(int=3))
    assert result.truncated_relevant_count == 1


def test_reset_clears_all_inherited_context() -> None:
    result = select_conversation_context(
        _request((_candidate(1), _candidate(2)), reset_context=True)
    )

    assert result.reset_applied is True
    assert result.selected_turn_ids == ()
    assert result.messages == ()
    assert result.excluded_irrelevant_count == 2


def test_inheritance_ineligible_turn_is_never_selected() -> None:
    result = select_conversation_context(
        _request(
            (
                _candidate(1),
                _candidate(2, inheritance_eligible=False),
            ),
            requires_immediate_context=True,
        )
    )

    assert result.selected_turn_ids == (UUID(int=1),)
    assert result.excluded_inheritance_count == 1


def test_context_is_explicitly_meaning_only_and_requires_fresh_retrieval() -> None:
    result = select_conversation_context(_request((_candidate(1),)))

    assert result.fact_authority == "none"
    assert result.requires_fresh_retrieval is True
    assert result.policy_version == CONTEXT_SELECTION_POLICY_VERSION


def test_equal_timestamps_have_stable_anchor_and_identity_order() -> None:
    first = _candidate(1).model_copy(
        update={
            "user_created_at": STARTED_AT,
            "assistant_created_at": STARTED_AT,
            "anchor_id": 3,
        }
    )
    second = _candidate(2).model_copy(
        update={
            "user_created_at": STARTED_AT,
            "assistant_created_at": STARTED_AT,
            "anchor_id": 2,
        }
    )

    result = select_conversation_context(_request((first, second)))

    assert result.selected_turn_ids == (second.turn_id, first.turn_id)


def test_selection_round_trip_and_json_are_deterministic() -> None:
    result = select_conversation_context(
        _request((_candidate(2), _candidate(1)))
    )

    serialized = conversation_context_json(result)

    assert ConversationContextSelection.model_validate_json(serialized) == result
    assert serialized == conversation_context_json(
        select_conversation_context(_request((_candidate(1), _candidate(2))))
    )
    assert json.loads(serialized)["fact_authority"] == "none"


def test_contracts_reject_duplicate_identity_and_ambiguous_reset() -> None:
    candidate = _candidate(1)
    with pytest.raises(ValidationError, match="candidate IDs"):
        _request((candidate, candidate))
    with pytest.raises(ValidationError, match="reset"):
        _request(
            (candidate,),
            reset_context=True,
            requires_immediate_context=True,
        )


def test_contracts_normalize_keys_and_reject_invalid_content_or_time() -> None:
    candidate = _candidate(1, keys=(" Entity:DSM ", "Jurisdiction: India"))
    request = _request(
        (candidate,),
        relevance_keys=(" ENTITY:DSM ",),
    )

    assert candidate.context_keys == ("entity:dsm", "jurisdiction: india")
    assert request.relevance_keys == ("entity:dsm",)
    with pytest.raises(ValidationError, match="unique"):
        _candidate(2, keys=("DSM", " dsm "))
    with pytest.raises(ValidationError):
        ConversationContextCandidate(
            **{
                **candidate.model_dump(mode="python"),
                "turn_id": UUID(int=99),
                "user_content": " ",
            }
        )
    with pytest.raises(ValidationError, match="timezone-aware"):
        ConversationContextCandidate(
            **{
                **candidate.model_dump(mode="python"),
                "turn_id": UUID(int=100),
                "user_created_at": datetime(2026, 7, 27, 8, 0),
            }
        )


def test_unknown_fields_and_out_of_range_budget_fail_closed() -> None:
    payload = _request((_candidate(1),)).model_dump(mode="python")
    payload["unknown"] = True
    with pytest.raises(ValidationError):
        ConversationContextRequest.model_validate(payload)
    with pytest.raises(ValidationError):
        _request((_candidate(1),), max_turns=0)
