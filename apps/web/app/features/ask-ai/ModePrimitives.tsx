import {
  AlertCircle,
  BookOpenCheck,
  Clock3,
  ExternalLink,
  FileSearch,
  Radio,
  Sparkles,
} from "lucide-react";
import type { ReactNode } from "react";

export const NO_OFFICIAL_DOCUMENTS_DISCLOSURE =
  "This explanation is generated from general AI knowledge because no sufficiently relevant official corpus evidence was selected for this question.";
export const OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE =
  "Official document search is temporarily unavailable. You can still view previously retrieved sources or search documents manually. Any explanation generated now will be labeled as general AI knowledge.";
export const NO_VERIFIED_LIVE_UPDATES_NOTICE =
  "No verified live updates were found for this period.";
export const LIVE_REFRESH_UNAVAILABLE_NOTICE =
  "Live sources could not be refreshed";

export type ModeConfidence = "High" | "Medium" | "Low" | "Unknown";
export type ModeState = "ready" | "pending" | "degraded" | "empty";
export type GeneralAiTrigger =
  | "healthy_official_no_match"
  | "official_retrieval_unavailable"
  | "explicit_general_question"
  | "optional_general_background";

type CommonBannerProps = {
  id: string;
  state?: ModeState;
};

export type KnowledgeModeBannerProps =
  | (CommonBannerProps & {
      mode: "grounded_regulatory";
      confidence: ModeConfidence;
      sourceCount: number;
      updatedAt?: string;
    })
  | (CommonBannerProps & {
      mode: "general_ai";
      confidence: Exclude<ModeConfidence, "High">;
      trigger: Exclude<GeneralAiTrigger, "official_retrieval_unavailable">;
    })
  | (CommonBannerProps & {
      mode: "general_ai";
      confidence: "Low" | "Unknown";
      trigger: "official_retrieval_unavailable";
    })
  | (CommonBannerProps & {
      mode: "live_intelligence";
      confidence: ModeConfidence;
      sourceCount: number;
      retrievedAt: string;
    });

const MODE_COPY = {
  grounded_regulatory: {
    title: "Official Regulatory Corpus",
    className: "official",
    Icon: BookOpenCheck,
  },
  general_ai: {
    title: "General AI Knowledge",
    className: "general",
    Icon: Sparkles,
  },
  live_intelligence: {
    title: "Live Web Sources",
    className: "live",
    Icon: Radio,
  },
} as const;

function pluralSources(count: number, qualifier = "") {
  const noun = count === 1 ? "source" : "sources";
  return `${count} ${qualifier}${noun}`;
}

function requireText(value: string, label: string) {
  if (!value.trim()) {
    throw new Error(`${label} cannot be blank`);
  }
}

function requireSourceCount(value: number) {
  if (!Number.isInteger(value) || value < 1) {
    throw new Error("Displayed evidence modes require a positive source count");
  }
}

function requireSafeTarget(value: string, label: string) {
  requireText(value, label);
  if (!/^(?:https?:\/\/|\/(?!\/))/i.test(value)) {
    throw new Error(`${label} must use an HTTP(S) or application path`);
  }
}

function requireAwareTimestamp(value: string, label: string) {
  requireText(value, label);
  if (
    !/(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ||
    Number.isNaN(Date.parse(value))
  ) {
    throw new Error(`${label} must be a timezone-aware timestamp`);
  }
}

function bannerMetadata(props: KnowledgeModeBannerProps) {
  if (props.mode === "grounded_regulatory") {
    requireSourceCount(props.sourceCount);
    if (props.updatedAt !== undefined) {
      requireText(props.updatedAt, "Official update label");
    }
    return [
      `${props.confidence} confidence`,
      pluralSources(props.sourceCount, "official "),
      ...(props.updatedAt ? [`Updated ${props.updatedAt}`] : []),
    ].join(" · ");
  }
  if (props.mode === "live_intelligence") {
    requireSourceCount(props.sourceCount);
    requireText(props.retrievedAt, "Live retrieval label");
    return [
      "Time-sensitive",
      pluralSources(props.sourceCount),
      `Retrieved ${props.retrievedAt}`,
    ].join(" · ");
  }
  const reason = {
    healthy_official_no_match:
      "No sufficiently relevant official corpus evidence selected",
    official_retrieval_unavailable: "Official verification unavailable",
    explicit_general_question: "General educational explanation",
    optional_general_background: "Background explanation",
  }[props.trigger];
  if (
    props.trigger === "official_retrieval_unavailable" &&
    props.confidence !== "Low" &&
    props.confidence !== "Unknown"
  ) {
    throw new Error("Official retrieval outage has a Low confidence ceiling");
  }
  return `${props.confidence} confidence · ${reason}`;
}

export function KnowledgeModeBanner(props: KnowledgeModeBannerProps) {
  requireText(props.id, "Mode banner ID");
  const copy = MODE_COPY[props.mode];
  const Icon = copy.Icon;
  const titleId = `${props.id}-mode-title`;

  return (
    <header
      className={`ask-mode-banner ${copy.className}`}
      data-mode={props.mode}
      data-state={props.state ?? "ready"}
      aria-labelledby={titleId}
    >
      <span className="ask-mode-icon" aria-hidden="true">
        <Icon size={19} />
      </span>
      <span className="ask-mode-copy">
        <strong id={titleId}>{copy.title}</strong>
        <span>{bannerMetadata(props)}</span>
      </span>
    </header>
  );
}

export function GeneralAiDisclosure({
  trigger,
}: {
  trigger: GeneralAiTrigger;
}) {
  const disclosure =
    trigger === "healthy_official_no_match"
      ? NO_OFFICIAL_DOCUMENTS_DISCLOSURE
      : trigger === "official_retrieval_unavailable"
        ? OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE
        : null;

  return disclosure ? (
    <p className="ask-mode-disclosure" data-trigger={trigger}>
      <strong>{disclosure}</strong>
    </p>
  ) : null;
}

export function KnowledgeModeSection({
  banner,
  manualSearchHref,
  children,
}: {
  banner: KnowledgeModeBannerProps;
  manualSearchHref?: string;
  children?: ReactNode;
}) {
  const requiresManualSearch =
    banner.mode === "general_ai" &&
    (banner.trigger === "healthy_official_no_match" ||
      banner.trigger === "official_retrieval_unavailable");
  if (requiresManualSearch && manualSearchHref === undefined) {
    throw new Error("General AI fallback requires manual document search");
  }
  if (!requiresManualSearch && manualSearchHref !== undefined) {
    throw new Error("Manual document search is limited to General AI fallback");
  }
  if (manualSearchHref !== undefined) {
    requireSafeTarget(manualSearchHref, "Manual search target");
  }

  return (
    <section
      className="ask-mode-section"
      aria-label={`${MODE_COPY[banner.mode].title} section`}
    >
      <KnowledgeModeBanner {...banner} />
      {banner.mode === "general_ai" ? (
        <GeneralAiDisclosure trigger={banner.trigger} />
      ) : null}
      {manualSearchHref ? (
        <a className="ask-mode-manual-search" href={manualSearchHref}>
          <FileSearch size={16} aria-hidden="true" />
          Search official documents manually
        </a>
      ) : null}
      {children ? <div className="ask-mode-content">{children}</div> : null}
    </section>
  );
}

export type LiveSourceCardProps = {
  title: string;
  publisher: string;
  sourceType: string;
  href: string;
  publishedAt: string;
  publishedLabel: string;
  retrievedAt: string;
  retrievedLabel: string;
  coverageNote?: string;
};

export function LiveSourceCard({
  title,
  publisher,
  sourceType,
  href,
  publishedAt,
  publishedLabel,
  retrievedAt,
  retrievedLabel,
  coverageNote,
}: LiveSourceCardProps) {
  for (const [value, label] of [
    [title, "Live source title"],
    [publisher, "Live source publisher"],
    [sourceType, "Live source type"],
    [publishedLabel, "Live publication label"],
    [retrievedLabel, "Live retrieval label"],
  ] as const) {
    requireText(value, label);
  }
  requireSafeTarget(href, "Live source URL");
  requireAwareTimestamp(publishedAt, "Live publication time");
  requireAwareTimestamp(retrievedAt, "Live retrieval time");

  return (
    <article className="ask-live-source-card">
      <div className="ask-live-source-heading">
        <span className="ask-live-source-type">{sourceType}</span>
        <h4>{title}</h4>
      </div>
      <dl className="ask-live-source-metadata">
        <div>
          <dt>Publisher</dt>
          <dd>{publisher}</dd>
        </div>
        <div>
          <dt>Published</dt>
          <dd>
            <time dateTime={publishedAt}>{publishedLabel}</time>
          </dd>
        </div>
        <div>
          <dt>Retrieved</dt>
          <dd>
            <time dateTime={retrievedAt}>{retrievedLabel}</time>
          </dd>
        </div>
      </dl>
      {coverageNote ? (
        <p className="ask-live-coverage-note">{coverageNote}</p>
      ) : null}
      <a
        className="ask-live-source-link"
        href={href}
        target="_blank"
        rel="noreferrer"
      >
        Open live source
        <ExternalLink size={15} aria-hidden="true" />
      </a>
      <p className="ask-live-trust-note">
        Live reporting does not establish official legal status.
      </p>
    </article>
  );
}

export type ModeStateKind =
  | "official_search_pending"
  | "official_search_unavailable"
  | "no_verified_live_updates"
  | "live_refresh_unavailable"
  | "general_ai_unavailable";

const STATE_COPY = {
  official_search_pending: {
    title: "Searching official sources",
    body: "Official evidence coverage is still being checked.",
    Icon: Clock3,
    className: "pending",
  },
  official_search_unavailable: {
    title: "Official search temporarily unavailable",
    body: OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
    Icon: FileSearch,
    className: "degraded",
  },
  no_verified_live_updates: {
    title: "No live updates found",
    body: NO_VERIFIED_LIVE_UPDATES_NOTICE,
    Icon: Radio,
    className: "empty",
  },
  live_refresh_unavailable: {
    title: LIVE_REFRESH_UNAVAILABLE_NOTICE,
    body: "Internal Regulatory Corpus research remains available.",
    Icon: AlertCircle,
    className: "degraded",
  },
  general_ai_unavailable: {
    title: "General explanation unavailable",
    body: "AI synthesis is temporarily unavailable. Retrieved evidence and manual document search remain available.",
    Icon: AlertCircle,
    className: "degraded",
  },
} as const;

export function ModeStatePanel({
  kind,
  manualSearchHref,
}: {
  kind: ModeStateKind;
  manualSearchHref?: string;
}) {
  const state = STATE_COPY[kind];
  const Icon = state.Icon;
  const isPending = kind === "official_search_pending";
  if (kind === "official_search_unavailable" && !manualSearchHref) {
    throw new Error("Official search outage requires manual search");
  }
  if (manualSearchHref !== undefined) {
    if (
      kind !== "official_search_unavailable" &&
      kind !== "general_ai_unavailable"
    ) {
      throw new Error("Manual search action does not belong to this state");
    }
    requireSafeTarget(manualSearchHref, "Manual search target");
  }

  return (
    <div
      className={`ask-mode-state ${state.className}`}
      role="status"
      aria-live={isPending ? "polite" : undefined}
      aria-atomic={isPending ? "true" : undefined}
    >
      <Icon size={20} aria-hidden="true" />
      <div>
        <h4>{state.title}</h4>
        <p>{state.body}</p>
        {manualSearchHref ? (
          <a className="ask-mode-state-action" href={manualSearchHref}>
            Search official documents manually
          </a>
        ) : null}
      </div>
    </div>
  );
}
