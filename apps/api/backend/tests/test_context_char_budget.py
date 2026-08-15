"""Context selection must fit Parallel's per-message character limit."""

from __future__ import annotations

from datetime import date

from backend.core import llm
from backend.rag.context_builder import (
    PARALLEL_MAX_MESSAGE_CHARS,
    PARALLEL_MAX_USER_MESSAGE_CHARS,
    build_context,
    grounded_user_prompt,
    max_prompt_context_chars,
)
from backend.rag.models import HybridRetrievalResult, Intent, RetrievalHit


def _hit(index: int, *, text: str | None = None, source: str = "vector") -> RetrievalHit:
    body = text or (
        f"Chunk {index} regulatory evidence. "
        + ("Transmission licensees shall comply with interconnection standards. " * 40)
    )
    return RetrievalHit(
        source=source,  # type: ignore[arg-type]
        document_id=100 + index,
        title=f"Regulatory Order {index}",
        source_url=f"https://example.gov.in/orders/{index}.pdf",
        issuer="CERC",
        issue_date=date(2024, 1, 15),
        chunk_id=1000 + index,
        page_number=index,
        section_title=f"Section {index}",
        text=body[:5000],
        final_score=1.0 - (index * 0.01),
    )


def _result(hits: list[RetrievalHit]) -> HybridRetrievalResult:
    return HybridRetrievalResult(
        query="What interconnection rules apply?",
        intent=Intent(
            name="obligation",
            query="What interconnection rules apply?",
            confidence=0.9,
            dominant_sources=("vector",),
        ),
        hits=hits,
        citations=[hit.citation() for hit in hits],
        related_questions=["What changed recently?"],
    )


def test_small_context_retains_all_evidence() -> None:
    hits = [_hit(i, text=f"Short evidence block {i}.") for i in range(1, 4)]
    context = build_context(
        _result(hits),
        max_prompt_chars=max_prompt_context_chars("What applies?"),
    )
    assert len(context.citations) == 3
    for index in range(1, 4):
        assert f"Evidence [{index}]" in context.prompt_context
        assert f"Short evidence block {index}." in context.prompt_context
        assert f"[{index}] Regulatory Order {index}" in context.prompt_context


def test_large_context_is_bounded_without_partial_blocks() -> None:
    hits = [_hit(i) for i in range(1, 15)]
    question = "What interconnection obligations apply to transmission licensees?"
    max_chars = max_prompt_context_chars(question)
    context = build_context(_result(hits), max_prompt_chars=max_chars)
    user_message = grounded_user_prompt(
        prompt_context=context.prompt_context,
        question=question,
    )

    assert 1 <= len(context.citations) < 14
    assert len(user_message) <= PARALLEL_MAX_USER_MESSAGE_CHARS
    assert len(user_message) < PARALLEL_MAX_MESSAGE_CHARS
    assert question in user_message

    # Retained evidence is a ranked prefix — never skip higher for lower.
    retained_ids = [citation.document_id for citation in context.citations]
    assert retained_ids == [100 + i for i in range(1, len(retained_ids) + 1)]

    # No partial evidence: every retained block keeps its Evidence text marker
    # and matching citation inventory entry.
    for index, citation in enumerate(context.citations, start=1):
        assert f"Evidence [{index}]" in context.prompt_context
        assert f"Document: {citation.title}" in context.prompt_context
        assert f"[{index}] {citation.title}" in context.prompt_context
        # Next excluded block must not appear.
    excluded = len(context.citations) + 1
    if excluded <= 14:
        assert f"Evidence [{excluded}]" not in context.prompt_context


def test_production_shape_fourteen_large_citations_fits_parallel_limit() -> None:
    """Reproduce prod: 14 large citations / ~7.5k word-tokens without char budget."""
    hits = [_hit(i) for i in range(1, 15)]
    unbounded = build_context(_result(hits), max_prompt_chars=None)
    question = "Summarise interconnection compliance duties with citations."
    unbounded_user = grounded_user_prompt(
        prompt_context=unbounded.prompt_context,
        question=question,
    )
    assert len(unbounded.citations) == 14
    assert unbounded.estimated_tokens > 4000
    assert len(unbounded_user) > PARALLEL_MAX_MESSAGE_CHARS

    bounded = build_context(
        _result(hits),
        max_prompt_chars=max_prompt_context_chars(question),
    )
    bounded_user = grounded_user_prompt(
        prompt_context=bounded.prompt_context,
        question=question,
    )
    assert bounded.citations
    assert len(bounded.citations) < 14
    assert len(bounded_user) <= PARALLEL_MAX_USER_MESSAGE_CHARS
    assert question in bounded_user
    assert "Evidence text:" in bounded.prompt_context


def test_user_question_always_retained_under_budget() -> None:
    hits = [_hit(i) for i in range(1, 12)]
    question = "Exact question text that must survive budgeting unchanged."
    context = build_context(
        _result(hits),
        max_prompt_chars=max_prompt_context_chars(question),
    )
    user_message = grounded_user_prompt(
        prompt_context=context.prompt_context,
        question=question,
    )
    assert question in user_message
    assert user_message.index(question) > user_message.index("Question:")


def test_history_does_not_inflate_grounded_user_message() -> None:
    hits = [_hit(i) for i in range(1, 15)]
    question = "Follow-up question about grid connectivity."
    context = build_context(
        _result(hits),
        max_prompt_chars=max_prompt_context_chars(question),
    )
    user_message = grounded_user_prompt(
        prompt_context=context.prompt_context,
        question=question,
    )
    history = [
        {"role": "user", "content": "Earlier question " + ("history " * 200)},
        {"role": "assistant", "content": "Earlier answer " + ("reply " * 200)},
    ]
    messages = llm._build_chat_completion_messages(
        system="system",
        user=user_message,
        history=history,
    )
    grounded = next(item for item in messages if item["content"] == user_message)
    assert len(grounded["content"]) <= PARALLEL_MAX_USER_MESSAGE_CHARS
    assert grounded["content"] == user_message
    assert "Earlier question" not in grounded["content"]


def test_highest_ranked_evidence_kept_first() -> None:
    hits = [_hit(i) for i in range(1, 10)]
    context = build_context(
        _result(hits),
        max_prompt_chars=8_000,
    )
    assert context.citations[0].document_id == 101
    assert [c.document_id for c in context.citations] == list(
        range(101, 101 + len(context.citations))
    )


def test_citation_metadata_stays_with_retained_evidence() -> None:
    hits = [_hit(i) for i in range(1, 8)]
    context = build_context(
        _result(hits),
        max_prompt_chars=max_prompt_context_chars("Metadata check"),
    )
    for index, citation in enumerate(context.citations, start=1):
        assert citation.source_url in context.prompt_context
        assert str(citation.chunk_id) in context.prompt_context
        assert f"[{index}] {citation.title}" in context.prompt_context
