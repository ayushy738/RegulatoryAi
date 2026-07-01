update regulatory_graph_extractions
set status = case
  when status in ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'SKIPPED') then status
  when status in ('AI_EXTRACTED', 'FALLBACK_EXTRACTED', 'HEURISTIC', 'AI') then 'COMPLETED'
  else 'FAILED'
end
where status is not null;

alter table regulatory_graph_extractions
  drop constraint if exists regulatory_graph_extractions_status_chk;

alter table regulatory_graph_extractions
  add constraint regulatory_graph_extractions_status_chk
  check (status in ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED', 'SKIPPED'));

create index if not exists regulatory_graph_extractions_status_idx
  on regulatory_graph_extractions (status, updated_at);
