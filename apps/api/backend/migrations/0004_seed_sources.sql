insert into sources (code, name, jurisdiction, url, crawler_type, allowed_domains, hint, enabled)
values
  (
    'mnre',
    'Ministry of New & Renewable Energy',
    'central',
    'https://mnre.gov.in/en/monthly-updates/',
    'digest',
    array['mnre.gov.in', 'cdnbbsr.s3waas.gov.in'],
    'Layer-1 digest source. Parse monthly policy and regulatory update PDFs, then fetch primary document links.',
    true
  ),
  (
    'cerc',
    'Central Electricity Regulatory Commission',
    'central',
    'https://cercind.gov.in/',
    'agent',
    array['cercind.gov.in'],
    'Tier-0 source. Audit listing structure before enabling live crawler.',
    true
  ),
  (
    'mop',
    'Ministry of Power',
    'central',
    'https://powermin.gov.in/en',
    'agent',
    array['powermin.gov.in'],
    'Tier-0 source. Audit PDF domains before enabling live crawler.',
    true
  )
on conflict (code) do update set
  name = excluded.name,
  jurisdiction = excluded.jurisdiction,
  url = excluded.url,
  crawler_type = excluded.crawler_type,
  allowed_domains = excluded.allowed_domains,
  hint = excluded.hint,
  enabled = excluded.enabled,
  updated_at = now();
