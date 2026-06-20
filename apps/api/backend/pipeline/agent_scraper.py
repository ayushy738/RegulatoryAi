from backend.core.models import DiscoveredDoc


async def scrape_source(source: dict) -> list[DiscoveredDoc]:
    """Discover candidate regulatory documents for non-digest sources.

    The full implementation will choose requests+BeautifulSoup or Playwright
    from the source audit result. This placeholder keeps the orchestrator
    contract stable before live network crawling is enabled.
    """

    return [
        DiscoveredDoc(
            source_code=source["code"],
            title=f"{source['name']} source audit placeholder",
            source_url=source["url"],
            issuing_body=source["name"],
            jurisdiction=source.get("jurisdiction"),
            doc_type="html",
            raw_summary="Source is configured; live discovery will run after audit.",
        )
    ]
