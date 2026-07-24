from backend.tools.dual_authentication import _prometheus


def test_prometheus_metrics_include_authentication_exchange_and_session_signals() -> None:
    output = _prometheus(
        {
            "authentication_last_24_hours": [
                {
                    "source": "supabase",
                    "outcome": "success",
                    "reason_code": None,
                    "observation_count": 12,
                },
                {
                    "source": "identity",
                    "outcome": "failure",
                    "reason_code": "SESSION_REVOKED",
                    "observation_count": 2,
                },
            ],
            "exchanges": {
                "exchanges_last_24_hours": 3,
                "exchanges_total": 9,
            },
            "sessions": {
                "active_sessions": 4,
                "revoked_sessions": 2,
                "expired_sessions": 1,
            },
        }
    )

    assert (
        'identity_authentication_observations_24h'
        '{source="supabase",outcome="success",reason=""} 12'
    ) in output
    assert (
        'identity_authentication_observations_24h'
        '{source="identity",outcome="failure",reason="SESSION_REVOKED"} 2'
    ) in output
    assert "identity_session_exchanges_24h 3" in output
    assert "identity_session_exchanges_total 9" in output
    assert "identity_active_sessions 4" in output
    assert "identity_revoked_sessions 2" in output
    assert "identity_expired_sessions 1" in output
