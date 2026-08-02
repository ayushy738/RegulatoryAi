alter table public.ask_claims
  add column claim_key text,
  add column verifier_provider text,
  add column verifier_version text,
  add column verifier_prompt_version text,
  add column verification_latency_ms integer,
  add column provenance jsonb,
  add column confidence_result jsonb;

update public.ask_claims
set claim_key = id::text
where claim_key is null;

alter table public.ask_claims
  alter column claim_key set not null,
  drop constraint ask_claims_support_status_chk,
  add constraint ask_claims_support_status_chk
    check (support_status in (
      'pending',
      'supported',
      'partially_supported',
      'unsupported',
      'contradictory',
      'unverifiable',
      'qualified',
      'not_applicable'
    )),
  add constraint ask_claims_verification_latency_chk
    check (
      verification_latency_ms is null
      or verification_latency_ms >= 0
    ),
  add constraint ask_claims_verifier_identity_bundle_chk
    check (
      (
        verifier_provider is null
        and verifier_version is null
        and verifier_prompt_version is null
      )
      or (
        verifier_provider is not null
        and verifier_version is not null
        and verifier_model is not null
        and verifier_prompt_version is not null
        and verifier_policy_version is not null
        and verification_latency_ms is not null
        and verifier_result is not null
      )
    ),
  add constraint ask_claims_structured_verifier_result_chk
    check (
      verifier_result is null
      or not (verifier_result ? 'schema_version')
      or (
        verifier_result ->> 'schema_version' = '1'
        and verifier_result ->> 'policy_version' = verifier_policy_version
        and verifier_result ->> 'claim_id' = claim_key
        and verifier_result -> 'verifier_identity' ->> 'provider'
          = verifier_provider
        and verifier_result -> 'verifier_identity' ->> 'verifier_version'
          = verifier_version
        and verifier_result -> 'verifier_identity' ->> 'model_version'
          = verifier_model
        and verifier_result -> 'verifier_identity' ->> 'prompt_version'
          = verifier_prompt_version
        and (verifier_result ->> 'latency_ms')::integer
          = verification_latency_ms
      )
    );

create unique index ask_claims_run_claim_key_idx
  on public.ask_claims (run_id, claim_key);

alter table public.ask_citations
  add column evidence_key text,
  add column verifier_provider text,
  add column verifier_version text,
  add column verifier_prompt_version text,
  add column verification_latency_ms integer,
  add column provenance jsonb;

update public.ask_citations citation
set evidence_key = source.source_key
from public.ask_sources source
where source.id = citation.source_id
  and source.run_id = citation.run_id
  and source.session_id = citation.session_id
  and source.user_id = citation.user_id
  and citation.evidence_key is null;

alter table public.ask_citations
  alter column evidence_key set not null,
  drop constraint ask_citations_verification_status_chk,
  add constraint ask_citations_verification_status_chk
    check (verification_status in (
      'pending',
      'verified',
      'supported',
      'partially_supported',
      'unsupported',
      'contradictory',
      'unverifiable',
      'rejected',
      'qualified',
      'not_applicable'
    )),
  add constraint ask_citations_verification_latency_chk
    check (
      verification_latency_ms is null
      or verification_latency_ms >= 0
    ),
  add constraint ask_citations_verifier_identity_bundle_chk
    check (
      (
        verifier_provider is null
        and verifier_version is null
        and verifier_prompt_version is null
      )
      or (
        verifier_provider is not null
        and verifier_version is not null
        and verifier_model is not null
        and verifier_prompt_version is not null
        and verifier_policy_version is not null
        and verification_latency_ms is not null
        and verifier_result is not null
      )
    ),
  add constraint ask_citations_structured_verifier_result_chk
    check (
      verifier_result is null
      or not (verifier_result ? 'schema_version')
      or (
        verifier_result ->> 'schema_version' = '1'
        and verifier_result ->> 'policy_version' = verifier_policy_version
        and verifier_result -> 'verifier_identity' ->> 'provider'
          = verifier_provider
        and verifier_result -> 'verifier_identity' ->> 'verifier_version'
          = verifier_version
        and verifier_result -> 'verifier_identity' ->> 'model_version'
          = verifier_model
        and verifier_result -> 'verifier_identity' ->> 'prompt_version'
          = verifier_prompt_version
        and (verifier_result ->> 'latency_ms')::integer
          = verification_latency_ms
      )
    );

create index ask_citations_run_evidence_claim_order_idx
  on public.ask_citations (run_id, evidence_key, claim_id, ordinal);

-- Rollback is feature-flag-first. The additive identity, verifier, provenance,
-- and confidence fields remain in place so previously rendered research stays
-- exactly restorable. Destructive column removal requires a later approved
-- contract migration after the compatibility window.
