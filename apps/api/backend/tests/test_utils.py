from backend.core.utils import canonical_url, sha256_normalized_text


def test_normalized_hash_collapses_whitespace_and_case() -> None:
    assert sha256_normalized_text(" Solar   Tariff ") == sha256_normalized_text("solar tariff")


def test_canonical_url_sorts_query_and_drops_fragment() -> None:
    assert canonical_url("HTTPS://Example.com//a?b=2&a=1#frag") == "https://example.com/a?a=1&b=2"
