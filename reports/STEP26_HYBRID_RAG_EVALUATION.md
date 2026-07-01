# Step 26 Hybrid RAG Evaluation

Generated at: 2026-06-30T17:55:55.144836+00:00

## Benchmark Summary

- Queries: 6
- Average retrieval latency ms: 2525.0
- Average chunks retrieved: 10.2
- Average Precision@5: 0.70
- Average Recall@10 proxy: 0.68
- Average citation accuracy proxy: 0.83
- Average grounding rate: 0.83
- Average false citation rate proxy: 0.17

## Query Results

| Query | Intent | Hits | Citations | Latency ms | P@5 | R@10 | Grounding |
|---|---|---:|---:|---:|---:|---:|---:|
| What changed today? | amendment | 0 | 0 | 4679 | 0.00 | 0.00 | 0.00 |
| Latest CERC amendment. | amendment | 15 | 15 | 2853 | 1.00 | 1.00 | 1.00 |
| Upcoming MNRE consultations. | consultation | 15 | 15 | 1929 | 0.20 | 1.00 | 1.00 |
| DSM amendment summary. | amendment | 1 | 1 | 1828 | 1.00 | 0.10 | 1.00 |
| Solar obligations. | obligation | 15 | 15 | 2000 | 1.00 | 1.00 | 1.00 |
| Transmission regulations. | regulation_lookup | 15 | 15 | 1861 | 1.00 | 1.00 | 1.00 |

## Notes

- Precision/recall are deterministic proxy metrics because no labeled gold set exists yet.
- Citation accuracy is counted as present/absent citation structure; manual regulatory review is still required for legal-grade accuracy.