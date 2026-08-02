from backend.pipeline.regulatory_knowledge_graph import (
    GraphInput,
    _catalog_alias_kind,
    _catalog_entity_class,
    _catalog_jurisdiction,
    _catalog_priority,
)


def test_catalog_sync_maps_graph_entities_to_glossary_constraints() -> None:
    assert _catalog_entity_class("ISSUER") == "regulator"
    assert _catalog_entity_class("REGULATION") == "legal_instrument"
    assert _catalog_entity_class("POLICY") == "scheme_or_policy"
    assert _catalog_entity_class("STAKEHOLDER") == "stakeholder"
    assert _catalog_entity_class("DEADLINE") == "status"

    assert _catalog_alias_kind("ISSUER") == "regulator_association"
    assert _catalog_alias_kind("REGULATION") == "regulation_family"
    assert _catalog_alias_kind("STAKEHOLDER") == "approved_alias"

    assert _catalog_priority("ISSUER") < _catalog_priority("DOCUMENT")


def test_catalog_sync_uses_document_jurisdiction_with_india_central_fallback() -> None:
    item = GraphInput(
        document_id=1,
        document_version_id=2,
        title="Test",
        issuer="CERC",
        source_url="https://example.test/doc.pdf",
        document_type="pdf",
        issue_date=None,
        content_hash="hash",
        text_content="text",
        content_length=4,
        jurisdiction="India/State",
    )
    fallback_item = GraphInput(
        document_id=1,
        document_version_id=2,
        title="Test",
        issuer="CERC",
        source_url="https://example.test/doc.pdf",
        document_type="pdf",
        issue_date=None,
        content_hash="hash",
        text_content="text",
        content_length=4,
    )

    assert _catalog_jurisdiction(item) == "India/State"
    assert _catalog_jurisdiction(fallback_item) == "India/Central"
