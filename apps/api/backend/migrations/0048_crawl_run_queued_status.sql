-- Phase 1 crawl lifecycle: allow crawl_runs to be created as queued before
-- background execution marks them running.
alter type run_status_t add value if not exists 'queued' before 'running';

alter table crawl_runs
  alter column status set default 'queued';
