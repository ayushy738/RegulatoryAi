alter table document_rag_status
  drop constraint if exists document_rag_status_status_check;

alter table document_rag_status
  drop constraint if exists document_rag_status_status_chk;

update document_rag_status
set status = 'RAG_READY',
    updated_at = now()
where status = 'READY';

alter table document_rag_status
  add constraint document_rag_status_status_chk
  check (status in ('PENDING', 'CHUNKED', 'EMBEDDING', 'RAG_READY', 'FAILED', 'SKIPPED'));
