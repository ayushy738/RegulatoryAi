from __future__ import annotations

from backend.core.config import settings
from backend.rag.chunker import estimate_tokens
from backend.rag.models import BuiltContext, Citation, HybridRetrievalResult, RetrievalHit


def build_context(result: HybridRetrievalResult) -> BuiltContext:
    token_budget = settings.rag_context_token_limit
    lines = [
        f"Detected intent: {result.intent.name}",
        "",
        "Retrieved evidence:",
    ]
    citations: list[Citation] = []
    used_tokens = estimate_tokens("\n".join(lines))
    for index, hit in enumerate(result.hits, start=1):
        citation = hit.citation()
        block = _evidence_block(index, hit, citation)
        block_tokens = estimate_tokens(block)
        if used_tokens + block_tokens > token_budget:
            break
        lines.append(block)
        used_tokens += block_tokens
        citations.append(citation)

    graph_facts = [hit for hit in result.hits if hit.source == "graph"]
    if graph_facts:
        lines.extend(["", "Knowledge graph facts:"])
        for hit in graph_facts[:10]:
            fact = f"- {hit.title}: {hit.text[:700]}"
            fact_tokens = estimate_tokens(fact)
            if used_tokens + fact_tokens > token_budget:
                break
            lines.append(fact)
            used_tokens += fact_tokens

    if citations:
        lines.extend(["", "Citation inventory:"])
        for index, citation in enumerate(citations, start=1):
            line = (
                f"[{index}] {citation.title} | issuer={citation.issuer or 'Unknown'} | "
                f"issue_date={citation.issue_date or 'Unknown'} | "
                f"url={citation.source_url} | chunk={citation.chunk_id or 'graph'} | "
                f"page={citation.page_number or 'unknown'}"
            )
            lines.append(line)
            used_tokens += estimate_tokens(line)

    return BuiltContext(
        prompt_context="\n".join(lines),
        citations=citations,
        graph_facts=graph_facts,
        related_questions=result.related_questions,
        estimated_tokens=used_tokens,
    )


def _evidence_block(index: int, hit: RetrievalHit, citation: Citation) -> str:
    return (
        f"\nEvidence [{index}]\n"
        f"Source type: {hit.source}\n"
        f"Document: {citation.title}\n"
        f"Issuer: {citation.issuer or 'Unknown'}\n"
        f"Issue date: {citation.issue_date or 'Unknown'}\n"
        f"Source URL: {citation.source_url}\n"
        f"Chunk/Page: chunk={citation.chunk_id or 'graph'}, "
        f"page={citation.page_number or 'unknown'}\n"
        f"Section: {citation.section_title or 'Unknown'}\n"
        f"Evidence text:\n{hit.text[:1800]}\n"
    )
