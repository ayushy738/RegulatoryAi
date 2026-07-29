from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.core.config import Settings

ASK_AI_FLAGS = {
    "ASK_AI_V2_WRITE_ENABLED": "ask_ai_v2_write_enabled",
    "ASK_AI_V2_API_ENABLED": "ask_ai_v2_api_enabled",
    "ASK_AI_DECISION_ENGINE_ENABLED": "ask_ai_decision_engine_enabled",
    "ASK_AI_ORCHESTRATOR_ENABLED": "ask_ai_orchestrator_enabled",
    "ASK_AI_GENERAL_MODE_ENABLED": "ask_ai_general_mode_enabled",
    "ASK_AI_LIVE_MODE_ENABLED": "ask_ai_live_mode_enabled",
    "ASK_AI_VERIFICATION_ENABLED": "ask_ai_verification_enabled",
    "ASK_AI_STREAMING_ENABLED": "ask_ai_streaming_enabled",
    "ASK_AI_V2_UI_ENABLED": "ask_ai_v2_ui_enabled",
}


def test_ask_ai_flags_default_off(monkeypatch: pytest.MonkeyPatch) -> None:
    for env_name in ASK_AI_FLAGS:
        monkeypatch.delenv(env_name, raising=False)

    configured = Settings(_env_file=None)

    assert {
        field_name: getattr(configured, field_name)
        for field_name in ASK_AI_FLAGS.values()
    } == dict.fromkeys(ASK_AI_FLAGS.values(), False)


@pytest.mark.parametrize(("env_name", "field_name"), ASK_AI_FLAGS.items())
def test_each_ask_ai_flag_can_be_enabled_independently(
    env_name: str,
    field_name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for candidate in ASK_AI_FLAGS:
        monkeypatch.delenv(candidate, raising=False)
    monkeypatch.setenv(env_name, "true")

    configured = Settings(_env_file=None)

    assert getattr(configured, field_name) is True
    assert all(
        getattr(configured, candidate_field) is False
        for candidate_field in ASK_AI_FLAGS.values()
        if candidate_field != field_name
    )


def test_invalid_ask_ai_flag_value_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ASK_AI_V2_API_ENABLED", "sometimes")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
