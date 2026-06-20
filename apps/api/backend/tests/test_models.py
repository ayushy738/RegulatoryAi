from backend.core.models import DiscoveredDoc


def test_discovered_doc_contract() -> None:
    doc = DiscoveredDoc(
        source_code="mnre",
        title="Solar tariff order",
        source_url="https://mnre.gov.in/en/monthly-updates/",
        jurisdiction="central",
    )
    assert doc.issue_date_precision == "unknown"
    assert doc.source_code == "mnre"
