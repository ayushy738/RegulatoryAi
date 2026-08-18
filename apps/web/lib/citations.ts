export type CitationLike = {
  document_id?: number | null;
  title?: string | null;
  issuer?: string | null;
  issue_date?: string | null;
  source_url?: string | null;
  section_title?: string | null;
  page_number?: number | null;
  evidence?: string | null;
};

export function citationKey(citation: CitationLike): string | null {
  return citationKeys(citation)[0] ?? null;
}

function citationKeys(citation: CitationLike): string[] {
  const keys: string[] = [];
  if (citation.document_id != null && Number.isFinite(citation.document_id)) {
    keys.push(`id:${citation.document_id}`);
  }
  const url = citation.source_url?.trim();
  if (url) keys.push(`url:${url}`);
  const title = citation.title?.trim().toLowerCase();
  if (title && keys.length === 0) keys.push(`title:${title}`);
  return keys;
}

/**
 * Collapse retrieved chunks that represent the same official document.
 * Prefer document identity, then source URL, then a normalised title.
 */
export function dedupeCitations<T extends CitationLike>(citations: T[]): T[] {
  const seen = new Set<string>();
  const unique: T[] = [];
  for (const citation of citations) {
    const keys = citationKeys(citation);
    if (!keys.length || keys.some((key) => seen.has(key))) continue;
    for (const key of keys) seen.add(key);
    unique.push(citation);
  }
  return unique;
}

/**
 * Answers often repeat a "Sources" heading that we already render from
 * structured citations. Strip that block so the conversation shows one list.
 */
export function stripEmbeddedSources(content: string, hasCitations: boolean): string {
  if (!hasCitations) return content;
  return content
    .replace(
      /\n*#{0,6}\s*Sources\s*\n(?:(?:\d+\.|[-*])\s.*(?:\n {2,}.*)*\n?)*/gi,
      "\n",
    )
    .replace(/\n*Sources\s*\n(?:\d+\..*(?:\n {3}.*)*)+/gi, "\n")
    .trim();
}
