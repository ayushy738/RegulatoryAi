"""Regression tests for OpenAI-compatible chat message construction."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from backend.core import llm


def test_messages_alternate_after_orphaned_user_history() -> None:
    """MODEL_UNAVAILABLE leaves a saved user row with no assistant reply."""
    messages = llm._build_chat_completion_messages(
        system="system",
        user="Current grounded question",
        history=[
            {"role": "user", "content": "Earlier question"},
            {"role": "assistant", "content": "Earlier answer"},
            {"role": "user", "content": "Failed attempt that never got an assistant reply"},
        ],
    )
    roles = [item["role"] for item in messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert messages[-1]["content"] == "Current grounded question"
    assert not _has_consecutive_same_roles(messages)


def test_messages_with_empty_history_are_system_then_user() -> None:
    messages = llm._build_chat_completion_messages(
        system="system",
        user="Only question",
        history=[],
    )
    assert [item["role"] for item in messages] == ["system", "user"]
    assert messages[-1]["content"] == "Only question"


def test_messages_preserve_complete_turns() -> None:
    messages = llm._build_chat_completion_messages(
        system="system",
        user="Follow-up",
        history=[
            {"role": "user", "content": "Q1"},
            {"role": "assistant", "content": "A1"},
            {"role": "user", "content": "Q2"},
            {"role": "assistant", "content": "A2"},
        ],
    )
    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "Q1"
    assert messages[2]["content"] == "A1"
    assert messages[-1]["content"] == "Follow-up"


def test_messages_merge_consecutive_same_roles_in_history() -> None:
    messages = llm._build_chat_completion_messages(
        system="system",
        user="Latest",
        history=[
            {"role": "user", "content": "U1"},
            {"role": "user", "content": "U2"},
            {"role": "assistant", "content": "A1"},
            {"role": "assistant", "content": "A2"},
        ],
    )
    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "U1" in messages[1]["content"]
    assert "U2" in messages[1]["content"]
    assert "A1" in messages[2]["content"]
    assert "A2" in messages[2]["content"]
    assert messages[-1]["content"] == "Latest"
    assert not _has_consecutive_same_roles(messages)


def test_messages_skip_leading_assistant_turns() -> None:
    messages = llm._build_chat_completion_messages(
        system="system",
        user="Question",
        history=[
            {"role": "assistant", "content": "Stray assistant"},
            {"role": "user", "content": "Prior"},
            {"role": "assistant", "content": "Prior answer"},
        ],
    )
    assert [item["role"] for item in messages] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert messages[1]["content"] == "Prior"


def test_parallel_client_posts_alternating_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url: str, **kwargs: Any) -> _Response:
        captured["url"] = url
        captured["json"] = kwargs["json"]
        return _Response()

    monkeypatch.setattr(llm.settings, "parallel_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_provider", "parallel")
    monkeypatch.setattr(llm.settings, "parallel_base_url", "https://api.parallel.ai")
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    client = llm.ParallelClient()
    reply = client.complete_text(
        system="sys",
        user="Current question with context",
        model="speed",
        history=[
            {"role": "user", "content": "orphan from failed request"},
        ],
    )

    assert reply == "ok"
    assert captured["url"] == "https://api.parallel.ai/chat/completions"
    roles = [item["role"] for item in captured["json"]["messages"]]
    assert roles == ["system", "user"]
    assert captured["json"]["messages"][-1]["content"] == "Current question with context"
    assert captured["json"]["model"] == "speed"
    assert captured["json"]["stream"] is False
    assert not _has_consecutive_same_roles(captured["json"]["messages"])


def test_parallel_client_still_surfaces_http_400(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = httpx.Request("POST", "https://api.parallel.ai/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        json={"error": {"message": "Messages must alternate between user and assistant roles"}},
    )

    def fake_post(*_: Any, **__: Any) -> httpx.Response:
        return response

    monkeypatch.setattr(llm.settings, "parallel_api_key", "test-key")
    monkeypatch.setattr(llm.settings, "llm_provider", "parallel")
    monkeypatch.setattr(llm.httpx, "post", fake_post)

    client = llm.ParallelClient()
    with pytest.raises(RuntimeError, match="HTTP 400"):
        client.complete_text(system="sys", user="q", model="speed", history=[])


def _has_consecutive_same_roles(messages: list[dict[str, str]]) -> bool:
    non_system = [item["role"] for item in messages if item["role"] != "system"]
    return any(
        left == right
        for left, right in zip(non_system, non_system[1:], strict=False)
    )
