# Step 26 RAG Readiness

Generated at: 2026-06-30

## Scope

- Audited the current chat flow, prompt construction, conversation history, retrieval logic, `document_texts`, knowledge graph, intelligence APIs, summaries, family registry, and version registry.
- No implementation code was changed before this report.
- Frontend, Azure deployment, WhatsApp, and non-RAG product surfaces are out of scope.

## Current Chat Flow

The existing `/chat` endpoint in `apps/api/backend/api/routes/chat.py` accepts `ChatRequest`, loads either the latest 5 events or a selected event, builds a simple text context from event title/body/topics/summary, calls `get_llm_client().complete_text`, saves plain chat messages, and returns `ChatResponse`.

Current flow:

1. User question enters `/chat`.
2. Optional `event_id` narrows context to one event.
3. Repository returns event summaries.
4. Prompt is built from event metadata and summaries only.
5. Parallel.ai is used when configured through the existing `LLMClient` factory.
6. User/assistant messages are persisted to `chat_messages`.

Readiness gap: there is no intent router, chunk retrieval, vector search, keyword search, graph retrieval composition, ranking, context builder, citation object, related-question payload, or retrieval metadata audit.

## Prompt Construction

Current prompt construction is summary-only:

- System prompt says to answer only from provided context.
- User prompt contains `Context:` and `Question:`.
- Context is event-level, not document/chunk-level.
- Citations are not enforced structurally.

Readiness gap: the prompt needs retrieved chunks, graph facts, deadlines, stakeholders, obligations, family/version history, citation instructions, insufficiency behavior, and token-budgeted context.

## Conversation History

Current history behavior:

- `chat_history()` returns recent rows from `chat_messages`.
- `/chat` sends the last 8 reversed messages to the LLM.
- `chat_messages` stores `user_id`, optional `event_id`, `role`, `content`, and `created_at`.

Readiness gap: there is no chat-session table and no retrieval metadata. Step 26 should persist detected intent, retrieved chunks, graph entities/facts used, citations returned, model, and latency per question.

## Retrieval Logic

Current retrieval is not real RAG:

- `/chat` calls `list_events()` or `get_event()`.
- There is no chunk table.
- There is no embedding provider.
- There is no vector store abstraction.
- There is no full-text search index for chunks.
- There is no hybrid ranker.

Readiness gap: build `EmbeddingProvider`, `VectorStore`, and `RetrievalProvider` abstractions, then expose `RetrievalProvider.hybrid_search()` to chat.

## Document Texts

`document_texts` exists and is populated from accepted primary documents:

- `content_hash`
- `text_content`
- `content_length`

`document_versions` connects documents to content hashes, raw files, extracted text paths, OCR flags, and fetch metadata.

Readiness: this is the correct source for chunking. The new chunker should reuse `document_texts` through latest or version-specific `document_versions`.

Gap: no `document_chunks`, no chunk status, and no RAG-ready marker.

## Knowledge Graph

Step 25 made the graph production-integrated:

- `regulatory_graph_entities`
- `regulatory_graph_document_entities`
- `regulatory_graph_edges`
- `regulatory_graph_stakeholders`
- `regulatory_graph_obligations`
- `regulatory_graph_deadlines`
- `regulatory_graph_extractions`
- `regulatory_graph_family_enrichment`

Readiness: graph rows can answer stakeholder, obligation, deadline, relationship, and family enrichment questions.

Gap: graph facts are not yet retrieved by chat and are not merged with chunk/vector/keyword results.

## Intelligence APIs

`/intelligence` currently exposes:

- `/deadlines`
- `/obligations`
- `/stakeholders`
- `/stakeholders/{stakeholder_slug}`
- `/readiness`

These are backed by `backend/core/intelligence_repository.py` and query graph deadlines, obligations, stakeholders, and graph-linked document refs.

Readiness: these queries provide patterns for graph retrieval and structured regulatory facts.

Gap: they are API-specific, not packaged as a retrieval provider used by chat.

## Summaries

The `summaries` table stores `summary_json` per event. The ingestion pipeline creates `SummaryPayload` and attaches event intelligence/change details before writing summaries.

Readiness: summaries should be a retrieval signal and context supplement.

Gap: summaries are currently event-facing only; they are not searched or included in RAG ranking.

## Family Registry

Step 18 tables exist:

- `document_families`
- `document_family_assignments`
- `document_version_registry`
- `document_version_relationships`
- `deadline_history`

Readiness: family and version lineage are available for amendment/history/comparison intents.

Gap: family/version retrieval is not exposed through a unified retrieval provider or ranker.

## Version Registry

`document_version_registry` tracks version labels, publication/effective dates, content hashes, parent/supersession references, amendment numbers, and referenced instruments.

Readiness: enough lineage exists to support amendment and comparison retrieval.

Gap: no context builder summarizes version history for the LLM.

## Embeddings Provider Investigation

The current codebase has a Parallel.ai chat-completions client but no embeddings implementation. Public/searchable documentation did not reveal a reliable Parallel.ai embeddings endpoint during this audit. Step 26 should still provide `ParallelEmbeddingProvider` behind an abstraction, but production configuration should be able to select an OpenAI-compatible embedding provider without business-logic changes.

## Recommended Insertion Points

Document ingestion:

1. Accepted primary document persists `documents`.
2. Text persists in `document_texts`.
3. Version persists in `document_versions`.
4. Family/version registry persists.
5. Knowledge graph persists.
6. New Step 26 background RAG indexing should enqueue chunking/embedding/vector indexing.
7. Event intelligence and event creation continue.

Chat:

1. `/chat` receives question.
2. Deterministic intent router classifies intent.
3. `RetrievalProvider.hybrid_search()` runs vector, keyword, graph, family/version, and summary retrieval.
4. Ranker returns top evidence.
5. Context builder creates grounded prompt context and citations.
6. Parallel.ai generates an answer.
7. Chat and retrieval metadata persist.

## Readiness Verdict

The backend is ready for Hybrid RAG implementation because primary document text, family/version lineage, event intelligence, and production knowledge graph rows exist. The missing layer is retrieval infrastructure: chunking, embeddings, pgvector storage, keyword search, graph/family retrieval composition, ranking, context building, citation metadata, background indexing, and chat audit metadata.
