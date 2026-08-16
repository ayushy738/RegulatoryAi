"""TODO — Parallel AI graph JSON contract (not part of crawl reliability fix).

Forensic finding (Run #58 / document 273):
  POST https://api.parallel.ai/chat/completions → HTTP 200
  → json.loads fails on message content
  → OfflineClient summary-shaped fallback
  → _looks_like_graph_payload fails
  → heuristic extraction with used_ai=false

Follow-ups (separate change):
  - Log truncated raw content on JSONDecodeError
  - Do not feed offline chat-summary schema into graph extraction
  - Align Parallel model/prompt with required graph keys
"""
