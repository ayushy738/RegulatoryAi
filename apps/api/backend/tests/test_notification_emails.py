"""Regulatory update email notification targeting, enqueue, and delivery."""

from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.core import email as email_mod
from backend.core.email import EmailDeliveryError, EmailResult
from backend.notifications import delivery, service, targeting, templates


class _Result:
    def __init__(self, rows: list[Any] | None = None, first_row: Any = None):
        self._rows = rows or []
        self._first = first_row

    def mappings(self):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._first


def test_targeting_matches_source_all_and_exclusions():
    session = MagicMock()
    cerc = 10
    rows = [
        {"user_id": "a", "email": "a@example.com"},
        {"user_id": "b", "email": "b@example.com"},
        {"user_id": "e", "email": "e@example.com"},
    ]
    session.execute.return_value = _Result(rows=rows)

    result = targeting.list_eligible_notification_recipients(session, source_id=cerc)
    assert [row["user_id"] for row in result] == ["a", "b", "e"]
    sql = str(session.execute.call_args.args[0])
    assert "email_enabled = true" in sql
    assert "instant" in sql.lower()
    assert "any(s.source_ids)" in sql


def test_targeting_without_source_only_all_subscribers():
    session = MagicMock()
    session.execute.return_value = _Result(rows=[{"user_id": "e", "email": "e@example.com"}])
    result = targeting.list_eligible_notification_recipients(session, source_id=None)
    assert result[0]["user_id"] == "e"
    sql = str(session.execute.call_args.args[0])
    assert "cardinality(s.source_ids) = 0" in sql


def test_enqueue_skips_non_new_changed_events(monkeypatch: pytest.MonkeyPatch):
    session = MagicMock()
    session.execute.return_value = _Result(first_row=None)

    @contextmanager
    def fake_scope():
        yield session

    monkeypatch.setattr(service, "session_scope", fake_scope)
    assert service.enqueue_notifications_for_event(event_id=99) == 0


def test_enqueue_creates_pending_rows_for_eligible_users(monkeypatch: pytest.MonkeyPatch):
    session = MagicMock()
    context = {
        "event_id": 101,
        "event_type": "NEW",
        "version_id": 5,
        "document_id": 9,
        "source_id": 10,
        "title": "CERC Order",
        "source_name": "CERC",
        "source_code": "cerc",
    }
    recipients = [
        {"user_id": "11111111-1111-1111-1111-111111111111", "email": "a@example.com"},
        {"user_id": "22222222-2222-2222-2222-222222222222", "email": "b@example.com"},
    ]
    inserted_ids = [SimpleNamespace(id=1), SimpleNamespace(id=2)]

    calls: list[str] = []

    def fake_execute(statement, params=None):  # noqa: ANN001
        sql = str(statement)
        calls.append(sql)
        if "from events e" in sql and "event_type" in sql:
            return _Result(first_row=context)
        if "insert into notifications_log" in sql:
            return _Result(first_row=inserted_ids.pop(0))
        return _Result()

    session.execute.side_effect = fake_execute
    monkeypatch.setattr(
        service,
        "list_eligible_notification_recipients",
        lambda *_a, **_k: recipients,
    )

    created = service.enqueue_notifications_for_event(event_id=101, session=session)
    assert created == 2
    assert any("on conflict" in sql.lower() for sql in calls)


def test_enqueue_idempotent_second_pass(monkeypatch: pytest.MonkeyPatch):
    session = MagicMock()
    context = {
        "event_id": 101,
        "event_type": "CHANGED",
        "version_id": 5,
        "document_id": 9,
        "source_id": 10,
        "title": "CERC Order",
        "source_name": "CERC",
        "source_code": "cerc",
    }

    def fake_execute(statement, params=None):  # noqa: ANN001
        sql = str(statement)
        if "from events e" in sql:
            return _Result(first_row=context)
        if "insert into notifications_log" in sql:
            return _Result(first_row=None)
        return _Result()

    session.execute.side_effect = fake_execute
    monkeypatch.setattr(
        service,
        "list_eligible_notification_recipients",
        lambda *_a, **_k: [
            {"user_id": "11111111-1111-1111-1111-111111111111", "email": "a@example.com"}
        ],
    )
    assert service.enqueue_notifications_for_event(event_id=101, session=session) == 0


def test_enqueue_notifications_batch_isolates_failures(monkeypatch: pytest.MonkeyPatch):
    calls: list[int] = []

    def fake_one(*, event_id: int, session=None):  # noqa: ANN001
        del session
        calls.append(event_id)
        if event_id == 2:
            raise RuntimeError("boom")
        return 1

    monkeypatch.setattr(service, "enqueue_notifications_for_event", fake_one)
    assert service.enqueue_notifications([1, 2, 3]) == 2
    assert calls == [1, 2, 3]


def test_email_template_new_and_changed_subjects():
    base = {
        "event_id": 42,
        "source_name": "CERC",
        "title": "Tariff order for solar",
        "raw_summary": "CERC issued a new tariff order.",
        "summary_json": {
            "plain_english_summary": "CERC issued a new tariff order affecting solar projects.",
            "why_it_matters": "Developers should review compliance timelines.",
            "affected_segments": [],
            "important_dates": [],
            "action_required": "monitor",
            "confidence": "high",
        },
        "issue_date": date(2026, 8, 16),
        "doc_type": "order",
        "detected_at": date(2026, 8, 16),
    }
    subject_new, html_new, text_new = templates.build_notification_email(
        {**base, "event_type": "NEW"}
    )
    assert subject_new.startswith("New CERC regulatory update:")
    assert "View Regulatory Update" in html_new
    assert "/events/42" in text_new
    assert "logo_wordmark.png" in html_new

    subject_changed, html_changed, _ = templates.build_notification_email(
        {**base, "event_type": "CHANGED"}
    )
    assert subject_changed.startswith("Regulatory update changed:")
    assert "What changed?" in html_changed


def test_brevo_send_uses_transactional_api(monkeypatch: pytest.MonkeyPatch):
    class FakeSettings:
        email_provider = "brevo"
        email_api_key = "test-key"
        email_from = "Resolven <updates@resolven.ai>"

    class FakeResponse:
        status_code = 201
        text = '{"messageId":"msg-1"}'

        def json(self):
            return {"messageId": "msg-1"}

    captured: dict[str, Any] = {}

    def fake_post(url, json=None, headers=None, timeout=None):  # noqa: ANN001
        del timeout
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return FakeResponse()

    monkeypatch.setattr(email_mod, "settings", FakeSettings())
    monkeypatch.setattr(email_mod.httpx, "post", fake_post)
    result = email_mod.send_email(
        to="user@example.com",
        subject="Hello",
        html="<p>Hi</p>",
        text="Hi",
    )
    assert result.provider == "brevo"
    assert result.message_id == "msg-1"
    assert captured["url"] == email_mod.BREVO_API_URL
    assert captured["headers"]["api-key"] == "test-key"
    assert captured["json"]["to"][0]["email"] == "user@example.com"


def test_brevo_failure_raises(monkeypatch: pytest.MonkeyPatch):
    class FakeSettings:
        email_provider = "brevo"
        email_api_key = "test-key"
        email_from = "updates@resolven.ai"

    class FakeResponse:
        status_code = 500
        text = "server error"

        def json(self):
            return {}

    monkeypatch.setattr(email_mod, "settings", FakeSettings())
    monkeypatch.setattr(email_mod.httpx, "post", lambda *a, **k: FakeResponse())
    with pytest.raises(EmailDeliveryError):
        email_mod.send_email(to="user@example.com", subject="x", html="<p>x</p>", text="x")


def test_offline_provider_never_calls_network(monkeypatch: pytest.MonkeyPatch):
    class FakeSettings:
        email_provider = "offline"
        email_api_key = None
        email_from = "updates@example.com"

    monkeypatch.setattr(email_mod, "settings", FakeSettings())

    def boom(*_a, **_k):
        raise AssertionError("network should not be used")

    monkeypatch.setattr(email_mod.httpx, "post", boom)
    result = email_mod.send_email(to="user@example.com", subject="x", html="<p>x</p>", text="x")
    assert result.provider == "offline"


def test_worker_marks_sent_and_continues_after_failure(monkeypatch: pytest.MonkeyPatch):
    claimed = [
        {
            "id": 1,
            "user_id": "11111111-1111-1111-1111-111111111111",
            "event_id": 10,
            "attempts": 0,
        },
        {
            "id": 2,
            "user_id": "22222222-2222-2222-2222-222222222222",
            "event_id": 11,
            "attempts": 0,
        },
    ]
    outcomes = {1: "sent", 2: "failed"}
    monkeypatch.setattr(delivery, "_claim_notifications", lambda *, limit: claimed)

    def fake_deliver(**kwargs):  # noqa: ANN003
        return outcomes[int(kwargs["notification_id"])]

    monkeypatch.setattr(delivery, "_deliver_one", fake_deliver)
    summary = delivery.process_pending_notifications(limit=10)
    assert summary["claimed"] == 2
    assert summary["sent"] == 1
    assert summary["failed"] == 1


def test_deliver_one_success_path(monkeypatch: pytest.MonkeyPatch):
    context = {
        "event_id": 10,
        "event_type": "NEW",
        "title": "Order",
        "source_name": "CERC",
        "raw_summary": "Summary",
        "summary_json": None,
        "issue_date": date(2026, 8, 16),
        "doc_type": "order",
        "detected_at": date(2026, 8, 16),
    }

    def fake_execute(statement, params=None):  # noqa: ANN001
        del params
        sql = str(statement)
        if "from profiles" in sql:
            return _Result(first_row={"email": "user@example.com"})
        return _Result()

    @contextmanager
    def scoped():
        session = MagicMock()
        session.execute.side_effect = fake_execute
        yield session

    monkeypatch.setattr(delivery, "session_scope", scoped)
    monkeypatch.setattr(
        delivery,
        "load_notification_email_context",
        lambda *_a, **_k: context,
    )
    monkeypatch.setattr(
        delivery,
        "send_email",
        lambda **_k: EmailResult(message_id="offline-1", provider="offline"),
    )
    status = delivery._deliver_one(
        notification_id=1,
        user_id="11111111-1111-1111-1111-111111111111",
        event_id=10,
        attempts=1,
    )
    assert status == "sent"
