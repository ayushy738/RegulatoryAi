from __future__ import annotations

from backend.core.config import settings
from backend.rag.chunker import estimate_tokens
from backend.rag.models import BuiltContext, Citation, HybridRetrievalResult, RetrievalHit

# Parallel Chat Completions rejects any single message over this many characters.
PARALLEL_MAX_MESSAGE_CHARS = 20_000
# Leave headroom for JSON encoding / provider-side counting differences.
PARALLEL_MESSAGE_CHAR_SAFETY_MARGIN = 1_000
PARALLEL_MAX_USER_MESSAGE_CHARS = (
    PARALLEL_MAX_MESSAGE_CHARS - PARALLEL_MESSAGE_CHAR_SAFETY_MARGIN
)

_GROUNDED_CONTEXT_PREFIX = "Conversation-aware retrieved context:\n"
_GROUNDED_QUESTION_PREFIX = "\n\nQuestion:\n"
_GROUNDED_QUESTION_SUFFIX = (
    "\n\nAnswer with grounded analysis and a short citation list."
)


def grounded_user_prompt(*, prompt_context: str, question: str) -> str:
    """Exact user message body sent to the LLM for grounded /chat answers."""
    return (
        f"{_GROUNDED_CONTEXT_PREFIX}{prompt_context}"
        f"{_GROUNDED_QUESTION_PREFIX}{question}"
        f"{_GROUNDED_QUESTION_SUFFIX}"
    )


def max_prompt_context_chars(
    question: str,
    *,
    max_user_message_chars: int = PARALLEL_MAX_USER_MESSAGE_CHARS,
) -> int:
    """Chars available for prompt_context after reserving wrapper + question."""
    overhead = len(grounded_user_prompt(prompt_context="", question=question))
    return max(0, max_user_message_chars - overhead)


def build_context(
    result: HybridRetrievalResult,
    *,
    max_prompt_chars: int | None = None,
) -> BuiltContext:
    """Select complete evidence blocks that fit token and optional char budgets.

    Retrieval may return more hits than fit. This layer keeps highest-ranked
    complete evidence blocks first and stops before exceeding budgets. Evidence
    text is never mid-cut beyond the existing per-block [:1800] cap.
    """
    token_budget = settings.rag_context_token_limit
    char_budget = max_prompt_chars
    header_lines = [
        f"Detected intent: {result.intent.name}",
        "",
        "Retrieved evidence:",
    ]
    selected_hits: list[RetrievalHit] = []
    citations: list[Citation] = []

    for hit in result.hits:
        citation = hit.citation()
        next_hits = [*selected_hits, hit]
        next_citations = [*citations, citation]
        prompt = _assemble_prompt_context(
            header_lines=header_lines,
            selected_hits=next_hits,
            citations=next_citations,
            graph_facts=[],
            include_graph_section=False,
        )
        if not _fits_budgets(
            prompt,
            token_budget=token_budget,
            char_budget=char_budget,
        ):
            break
        selected_hits.append(hit)
        citations.append(citation)

    graph_candidates = [hit for hit in result.hits if hit.source == "graph"]
    selected_graph_facts: list[RetrievalHit] = []
    if graph_candidates and citations:
        for hit in graph_candidates[:10]:
            next_graph = [*selected_graph_facts, hit]
            prompt = _assemble_prompt_context(
                header_lines=header_lines,
                selected_hits=selected_hits,
                citations=citations,
                graph_facts=next_graph,
                include_graph_section=True,
            )
            if not _fits_budgets(
                prompt,
                token_budget=token_budget,
                char_budget=char_budget,
            ):
                break
            selected_graph_facts.append(hit)

    prompt_context = _assemble_prompt_context(
        header_lines=header_lines,
        selected_hits=selected_hits,
        citations=citations,
        graph_facts=selected_graph_facts,
        include_graph_section=bool(selected_graph_facts),
    )
    return BuiltContext(
        prompt_context=prompt_context,
        citations=citations,
        graph_facts=selected_graph_facts,
        related_questions=result.related_questions,
        estimated_tokens=estimate_tokens(prompt_context),
    )


def _fits_budgets(
    prompt: str,
    *,
    token_budget: int,
    char_budget: int | None,
) -> bool:
    if estimate_tokens(prompt) > token_budget:
        return False
    if char_budget is not None and len(prompt) > char_budget:
        return False
    return True


def _assemble_prompt_context(
    *,
    header_lines: list[str],
    selected_hits: list[RetrievalHit],
    citations: list[Citation],
    graph_facts: list[RetrievalHit],
    include_graph_section: bool,
) -> str:
    lines = list(header_lines)
    for index, hit in enumerate(selected_hits, start=1):
        lines.append(_evidence_block(index, hit, citations[index - 1]))

    if include_graph_section and graph_facts:
        lines.extend(["", "Knowledge graph facts:"])
        for hit in graph_facts:
            lines.append(f"- {hit.title}: {hit.text[:700]}")

    if citations:
        lines.extend(["", "Citation inventory:"])
        for index, citation in enumerate(citations, start=1):
            lines.append(_citation_inventory_line(index, citation))
    return "\n".join(lines)


def _citation_inventory_line(index: int, citation: Citation) -> str:
    return (
        f"[{index}] {citation.title} | issuer={citation.issuer or 'Unknown'} | "
        f"issue_date={citation.issue_date or 'Unknown'} | "
        f"url={citation.source_url} | chunk={citation.chunk_id or 'graph'} | "
        f"page={citation.page_number or 'unknown'}"
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
