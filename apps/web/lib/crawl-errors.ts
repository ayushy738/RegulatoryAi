/**
 * Turns raw crawl-run error payloads into human-readable diagnostics.
 *
 * The pipeline serialises failures as `{error, error_type, error_message,
 * error_repr, error_args}` plus page context, and empty-selection failures add
 * configuration diagnosis keys. Operators should never have to read that JSON to
 * understand what broke, so we classify it into a small set of categories with a
 * plain-language title, an explanation, and a retryability verdict.
 *
 * The raw payload is always preserved on `raw` so it can be shown behind a
 * "Technical details" disclosure.
 */

export type CrawlErrorCategory =
  | "dns"
  | "tls"
  | "http_client"
  | "http_server"
  | "timeout"
  | "connection"
  | "parser"
  | "validation"
  | "configuration"
  | "unknown";

export type Retryability = "retryable" | "not_retryable" | "needs_configuration";

export type ClassifiedCrawlError = {
  category: CrawlErrorCategory;
  /** Short human-readable headline, e.g. "Secure connection could not be verified". */
  title: string;
  /** One or two sentences explaining what happened, in operator language. */
  explanation: string;
  retryability: Retryability;
  /** Labelled facts worth surfacing above the raw payload. */
  facts: Array<{ label: string; value: string }>;
  affectedPage: string | null;
  sourceCode: string | null;
  httpStatus: number | null;
  host: string | null;
  raw: Record<string, unknown>;
};

const RETRYABILITY_LABEL: Record<Retryability, string> = {
  retryable: "Safe to retry",
  not_retryable: "Retrying will not help",
  needs_configuration: "Needs configuration change",
};

export function retryabilityLabel(value: Retryability) {
  return RETRYABILITY_LABEL[value];
}

function text(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function firstString(raw: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = text(raw[key]);
    if (value) return value;
  }
  return "";
}

function extractHost(raw: Record<string, unknown>, haystack: string): string | null {
  const explicit = firstString(raw, ["host", "hostname"]);
  if (explicit) return explicit;

  const url = firstString(raw, ["url", "source_url", "page_url", "source_page_url"]);
  if (url) {
    try {
      return new URL(url).hostname;
    } catch {
      /* fall through to the message scan */
    }
  }

  // Messages commonly embed "host='gercin.org'" or a bare domain.
  const quoted = haystack.match(/host(?:name)?[=:]\s*'?"?([a-z0-9.-]+\.[a-z]{2,})/i);
  if (quoted?.[1]) return quoted[1];
  const bare = haystack.match(/\b((?:[a-z0-9-]+\.)+[a-z]{2,})\b/i);
  return bare?.[1] ?? null;
}

function extractHttpStatus(
  raw: Record<string, unknown>,
  haystack: string,
): number | null {
  for (const key of ["status", "status_code", "http_status", "response_status"]) {
    const value = raw[key];
    if (typeof value === "number" && value >= 100 && value < 600) return value;
    const parsed = Number.parseInt(text(value), 10);
    if (Number.isFinite(parsed) && parsed >= 100 && parsed < 600) return parsed;
  }
  const match = haystack.match(/\b(?:http\s*|status(?:\s*code)?[:\s]*)([1-5]\d{2})\b/i);
  if (match?.[1]) return Number.parseInt(match[1], 10);
  return null;
}

function extractAttempts(raw: Record<string, unknown>): string | null {
  const attempt = raw.attempt ?? raw.attempts;
  const max = raw.max_attempts ?? raw.attempt_limit ?? raw.retries;
  if (attempt === undefined || attempt === null) return null;
  return max === undefined || max === null
    ? String(attempt)
    : `${attempt} of ${max}`;
}

type Rule = {
  category: CrawlErrorCategory;
  matches: (haystack: string, type: string, status: number | null) => boolean;
  title: string;
  explanation: (context: { host: string | null; status: number | null }) => string;
  retryability: Retryability;
};

/** Ordered most-specific first: the first matching rule wins. */
const RULES: Rule[] = [
  {
    category: "tls",
    matches: (haystack) =>
      /certificate|ssl|tls|sslerror|cert_?verify|hostname mismatch|self.signed/i.test(
        haystack,
      ),
    title: "Secure connection could not be verified",
    explanation: ({ host }) =>
      `The TLS certificate presented by ${host ?? "the source host"} could not be validated, so the crawler refused to continue. This is usually an expired, misissued or incomplete certificate chain on the source website.`,
    retryability: "not_retryable",
  },
  {
    category: "dns",
    matches: (haystack) =>
      /name or service not known|nodename nor servname|getaddrinfo|dns|enotfound|name resolution/i.test(
        haystack,
      ),
    title: "Website address could not be resolved",
    explanation: ({ host }) =>
      `DNS lookup for ${host ?? "the source host"} failed, so the crawler never reached the website. The domain may have changed, lapsed, or be temporarily unresolvable.`,
    retryability: "retryable",
  },
  {
    category: "timeout",
    matches: (haystack, type) =>
      /timeout|timed out|readtimeout|connecttimeout|deadline exceeded/i.test(
        `${haystack} ${type}`,
      ),
    title: "Source did not respond in time",
    explanation: ({ host }) =>
      `${host ?? "The source website"} did not respond before the crawl timeout elapsed. Slow government portals frequently succeed on a later run.`,
    retryability: "retryable",
  },
  {
    category: "http_client",
    matches: (_haystack, _type, status) => status !== null && status >= 400 && status < 500,
    title: "Source rejected the request",
    explanation: ({ status, host }) => {
      if (status === 404) {
        return `${host ?? "The source"} returned 404 Not Found. The monitored page URL has most likely moved and needs updating.`;
      }
      if (status === 403 || status === 401) {
        return `${host ?? "The source"} returned ${status}, refusing access. The page may be behind a login, geo-block or bot filter.`;
      }
      if (status === 429) {
        return `${host ?? "The source"} returned 429 Too Many Requests. The crawler is being rate limited and should back off.`;
      }
      return `${host ?? "The source"} returned HTTP ${status}, rejecting the request.`;
    },
    retryability: "needs_configuration",
  },
  {
    category: "http_server",
    matches: (_haystack, _type, status) => status !== null && status >= 500,
    title: "Source website returned a server error",
    explanation: ({ status, host }) =>
      `${host ?? "The source website"} returned HTTP ${status}. The failure is on the source side, not in the crawl configuration.`,
    retryability: "retryable",
  },
  {
    category: "connection",
    matches: (haystack, type) =>
      /connection (?:reset|refused|aborted|error)|econnreset|econnrefused|remote end closed|broken pipe|connectionerror/i.test(
        `${haystack} ${type}`,
      ),
    title: "Connection to the source was interrupted",
    explanation: ({ host }) =>
      `The network connection to ${host ?? "the source host"} was closed before the response completed.`,
    retryability: "retryable",
  },
  {
    category: "configuration",
    matches: (haystack, type) =>
      /no (?:enabled |crawlable )?(?:source )?pages|not permitted for source|allowed domain|disabled|selection (?:is )?empty|sourcepagepolicy/i.test(
        `${haystack} ${type}`,
      ),
    title: "Nothing was eligible to crawl",
    explanation: () =>
      "The run started but no monitored page was eligible for this source. Check that the source is enabled, has at least one enabled page, and that each page URL is within the source's allowed domains.",
    retryability: "needs_configuration",
  },
  {
    category: "parser",
    matches: (haystack, type) =>
      /parse|parser|pdf|extract|decode|unicode|malformed|beautifulsoup|lxml|unsupported (?:media|content) type/i.test(
        `${haystack} ${type}`,
      ),
    title: "Document could not be read",
    explanation: () =>
      "The document was downloaded but its contents could not be extracted. This is usually a scanned image, an encrypted PDF, or an unexpected file format.",
    retryability: "not_retryable",
  },
  {
    category: "validation",
    matches: (haystack, type) =>
      /validation|invalid|schema|pydantic|required field|failed to validate/i.test(
        `${haystack} ${type}`,
      ),
    title: "Extracted data failed validation",
    explanation: () =>
      "The crawler retrieved content but the extracted record did not satisfy the expected shape, so it was rejected rather than persisted.",
    retryability: "not_retryable",
  },
];

/** Human-readable label for a category, for grouping headers. */
export const CATEGORY_LABEL: Record<CrawlErrorCategory, string> = {
  dns: "DNS failure",
  tls: "TLS certificate failure",
  http_client: "HTTP client error",
  http_server: "HTTP server error",
  timeout: "Timeout",
  connection: "Connection failure",
  parser: "Parser failure",
  validation: "Validation failure",
  configuration: "Configuration issue",
  unknown: "Unclassified failure",
};

export function classifyCrawlError(
  entry: Record<string, unknown>,
): ClassifiedCrawlError {
  const raw = entry ?? {};
  const message = firstString(raw, [
    "error",
    "error_message",
    "message",
    "detail",
    "reason",
  ]);
  const errorType = firstString(raw, ["error_type", "type", "exception"]);
  const repr = firstString(raw, ["error_repr"]);
  const haystack = `${message} ${errorType} ${repr}`.trim();

  const host = extractHost(raw, haystack);
  const httpStatus = extractHttpStatus(raw, haystack);
  const rule =
    RULES.find((candidate) => candidate.matches(haystack, errorType, httpStatus)) ??
    null;

  const affectedPage =
    firstString(raw, ["source_page", "page_name", "page"]) || null;
  const sourceCode = firstString(raw, ["source", "source_code"]) || null;

  const facts: Array<{ label: string; value: string }> = [];
  if (host) facts.push({ label: "Host", value: host });
  if (httpStatus !== null) facts.push({ label: "HTTP status", value: String(httpStatus) });
  const attempts = extractAttempts(raw);
  if (attempts) facts.push({ label: "Attempt", value: attempts });
  if (affectedPage) facts.push({ label: "Page", value: affectedPage });
  if (sourceCode) facts.push({ label: "Source", value: sourceCode });
  if (errorType) facts.push({ label: "Error type", value: errorType });

  // Configuration diagnosis keys, when the pipeline recorded an empty selection.
  for (const [key, label] of [
    ["configured_pages", "Configured pages"],
    ["enabled_pages", "Enabled pages"],
    ["crawlable_pages", "Crawlable pages"],
  ] as const) {
    const value = raw[key];
    if (typeof value === "number") facts.push({ label, value: String(value) });
  }

  if (!rule) {
    return {
      category: "unknown",
      title: message
        ? truncate(message, 120)
        : "The crawler reported an unclassified failure",
      explanation:
        "This failure did not match a known category. The technical details below contain the raw payload recorded by the pipeline.",
      retryability: "retryable",
      facts,
      affectedPage,
      sourceCode,
      httpStatus,
      host,
      raw,
    };
  }

  return {
    category: rule.category,
    title: rule.title,
    explanation: rule.explanation({ host, status: httpStatus }),
    retryability: rule.retryability,
    facts,
    affectedPage,
    sourceCode,
    httpStatus,
    host,
    raw,
  };
}

function truncate(value: string, max: number) {
  return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}

export function classifyCrawlErrors(
  entries: Array<Record<string, unknown>> | undefined | null,
): ClassifiedCrawlError[] {
  if (!Array.isArray(entries)) return [];
  return entries.map(classifyCrawlError);
}

/**
 * Collapse repeated identical failures so an operator sees "TLS failure on 3
 * pages" rather than three near-identical blocks.
 */
export function groupCrawlErrors(errors: ClassifiedCrawlError[]) {
  const groups = new Map<
    string,
    { category: CrawlErrorCategory; title: string; items: ClassifiedCrawlError[] }
  >();
  for (const error of errors) {
    const key = `${error.category}::${error.title}`;
    const existing = groups.get(key);
    if (existing) {
      existing.items.push(error);
    } else {
      groups.set(key, {
        category: error.category,
        title: error.title,
        items: [error],
      });
    }
  }
  return Array.from(groups.values());
}
