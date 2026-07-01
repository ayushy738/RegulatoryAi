from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from backend.rag.retrieval import RetrievalProviderFactory

REPORT_PATH = Path("E:/RegulatoryAi/reports/STEP26_HYBRID_RAG_EVALUATION.md")

BENCHMARK_QUERIES = [
    "What changed today?",
    "Latest CERC amendment.",
    "Upcoming MNRE consultations.",
    "DSM amendment summary.",
    "Solar obligations.",
    "Transmission regulations.",
]


def main() -> None:
    provider = RetrievalProviderFactory.get_provider()
    rows = []
    for query in BENCHMARK_QUERIES:
        result = provider.hybrid_search(query, limit=15)
        rows.append(
            {
                "query": query,
                "intent": result.intent.name,
                "hits": len(result.hits),
                "citations": len(result.citations),
                "latency_ms": result.retrieval_latency_ms,
                "precision_at_5": _precision_at_k(result.hits, query, 5),
                "recall_at_10": _recall_proxy(result.hits, 10),
                "citation_accuracy": 1.0 if result.citations else 0.0,
                "grounding_rate": 1.0 if result.hits and result.citations else 0.0,
                "false_citation_rate": 0.0 if result.citations else 1.0,
            }
        )

    report = _markdown(rows)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(report)


def _precision_at_k(hits, query: str, k: int) -> float:
    top = hits[:k]
    if not top:
        return 0.0
    terms = {term.lower() for term in query.split() if len(term) > 3}
    if not terms:
        return 1.0
    relevant = 0
    for hit in top:
        haystack = f"{hit.title} {hit.text}".lower()
        if any(term in haystack for term in terms):
            relevant += 1
    return relevant / len(top)


def _recall_proxy(hits, k: int) -> float:
    return min(1.0, len(hits[:k]) / max(1, k))


def _markdown(rows: list[dict]) -> str:
    latency_values = [row["latency_ms"] for row in rows]
    lines = [
        "# Step 26 Hybrid RAG Evaluation",
        "",
        f"Generated at: {datetime.now(UTC).isoformat()}",
        "",
        "## Benchmark Summary",
        "",
        f"- Queries: {len(rows)}",
        f"- Average retrieval latency ms: {mean(latency_values):.1f}",
        f"- Average chunks retrieved: {mean(row['hits'] for row in rows):.1f}",
        f"- Average Precision@5: {mean(row['precision_at_5'] for row in rows):.2f}",
        f"- Average Recall@10 proxy: {mean(row['recall_at_10'] for row in rows):.2f}",
        f"- Average citation accuracy proxy: "
        f"{mean(row['citation_accuracy'] for row in rows):.2f}",
        f"- Average grounding rate: {mean(row['grounding_rate'] for row in rows):.2f}",
        f"- Average false citation rate proxy: "
        f"{mean(row['false_citation_rate'] for row in rows):.2f}",
        "",
        "## Query Results",
        "",
        "| Query | Intent | Hits | Citations | Latency ms | P@5 | R@10 | Grounding |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in rows:
        lines.append(
            f"| {row['query']} | {row['intent']} | {row['hits']} | "
            f"{row['citations']} | {row['latency_ms']} | "
            f"{row['precision_at_5']:.2f} | {row['recall_at_10']:.2f} | "
            f"{row['grounding_rate']:.2f} |"
        )
    lines.extend(
        [
            "",
            "## Notes",
            "",
            "- Precision/recall are deterministic proxy metrics because no labeled gold set "
            "exists yet.",
            "- Citation accuracy is counted as present/absent citation structure; manual "
            "regulatory review is still required for legal-grade accuracy.",
        ]
    )
    return "\n".join(lines)


if __name__ == "__main__":
    main()
