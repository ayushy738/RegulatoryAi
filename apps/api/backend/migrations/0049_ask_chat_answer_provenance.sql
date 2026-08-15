-- Ask AI conversation restoration integrity.
--
-- chat_retrieval_audit previously carried only (user_id, question, citations),
-- so restoring a conversation had to match an assistant answer to its sources
-- by user question text. Two conversations that ask the same question could
-- therefore render each other's citations. Bind each audit row to the exact
-- assistant message it explains.
--
-- knowledge_basis (official | general | none) was returned live but never
-- persisted, so a refreshed conversation could not reproduce the original
-- answer semantics. Store it on the assistant message itself, which is the one
-- row every answer path writes.
alter table public.chat_retrieval_audit
  add column assistant_message_id bigint
    references public.chat_messages(id) on delete set null;

create index if not exists chat_retrieval_audit_assistant_message_idx
  on public.chat_retrieval_audit (assistant_message_id)
  where assistant_message_id is not null;

alter table public.chat_messages
  add column knowledge_basis text,
  add constraint chat_messages_knowledge_basis_chk
    check (
      knowledge_basis is null
      or knowledge_basis in ('official', 'general', 'none')
    );

-- Historical audit rows keep assistant_message_id null and historical assistant
-- messages keep knowledge_basis null. Those rows cannot be associated exactly
-- after the fact, because the pre-0049 schema never recorded which answer a
-- retrieval audit belonged to. Restoration therefore uses the question-text
-- fallback only for messages that predate this migration, and never lets a
-- message-bound audit row be reached by text matching.
