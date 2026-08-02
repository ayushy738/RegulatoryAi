"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

import {
  askCitationSelectionSchema,
  type AskCitationSelection,
} from "../../../lib/ask-ai-citations";
import {
  askCitationDetailSchema,
  type AskCitationDetail,
} from "../../../lib/ask-ai-evidence";

const TERMINAL_VERIFICATION_STATES = new Set([
  "supported",
  "partially_supported",
  "contradictory",
  "unverifiable",
]);

const VERIFICATION_COPY: Record<string, string> = {
  supported: "Supported",
  partially_supported: "Partially supported",
  contradictory: "Contradictory",
  unverifiable: "Unverifiable",
};

const SOURCE_STATUS_COPY: Record<
  AskCitationDetail["current_source_status"],
  string
> = {
  current: "Current source",
  superseded: "Superseded source",
  available_unclassified: "Source available — status not classified",
  not_applicable: "Current status not applicable",
};

export type CitationDetailLoader = (
  messageId: string,
  citationId: string,
) => Promise<unknown>;

type InlineCitationProps = {
  selection: AskCitationSelection;
  onInspect?: (selection: AskCitationSelection) => void;
};

export function InlineCitation({
  selection,
  onInspect,
}: InlineCitationProps) {
  const safeSelection = askCitationSelectionSchema.parse(selection);
  const terminal = TERMINAL_VERIFICATION_STATES.has(
    safeSelection.verification_status,
  );
  const statusCopy =
    VERIFICATION_COPY[safeSelection.verification_status] ??
    (safeSelection.verification_status === "pending"
      ? "Verifying citation…"
      : "Citation unavailable");

  if (!terminal || !onInspect) {
    return (
      <span
        className="ask-inline-citation ask-inline-citation-static"
        data-verification-state={safeSelection.verification_status}
        aria-label={`${safeSelection.marker} ${statusCopy}`}
      >
        {safeSelection.marker} {statusCopy}
      </span>
    );
  }

  return (
    <button
      type="button"
      className="ask-inline-citation"
      data-verification-state={safeSelection.verification_status}
      aria-label={`Inspect citation ${safeSelection.marker} — ${statusCopy}`}
      onClick={() => onInspect(safeSelection)}
    >
      <span aria-hidden="true">{safeSelection.marker}</span>
      <span className="ask-inline-citation-state">{statusCopy}</span>
    </button>
  );
}

type CitationEvidencePanelProps = {
  selection: AskCitationSelection;
  loadDetail: CitationDetailLoader;
  onClose: () => void;
  onSaveCitation?: (selection: AskCitationSelection) => void;
};

export function CitationEvidencePanel({
  selection,
  loadDetail,
  onClose,
  onSaveCitation,
}: CitationEvidencePanelProps) {
  const safeSelection = useMemo(
    () => askCitationSelectionSchema.parse(selection),
    [selection],
  );
  const [detail, setDetail] = useState<AskCitationDetail | null>(null);
  const [loadState, setLoadState] = useState<"loading" | "ready" | "error">(
    "loading",
  );
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const generatedId = useId().replaceAll(":", "");
  const claimTitleId = `ask-citation-claim-${generatedId}`;
  const sourceTitleId = `ask-citation-source-${generatedId}`;
  const excerptTitleId = `ask-citation-excerpt-${generatedId}`;

  useEffect(() => {
    let current = true;
    setDetail(null);
    setLoadState("loading");
    void loadDetail(safeSelection.message_id, safeSelection.citation_id)
      .then((value) => {
        const parsed = askCitationDetailSchema.parse(value);
        assertDetailMatchesSelection(parsed, safeSelection);
        if (current) {
          setDetail(parsed);
          setLoadState("ready");
        }
      })
      .catch(() => {
        if (current) setLoadState("error");
      });
    return () => {
      current = false;
    };
  }, [loadDetail, safeSelection]);

  useEffect(() => {
    closeButtonRef.current?.focus();
  }, [safeSelection.citation_id]);

  const source = detail?.source;
  const title = source?.title_snapshot ?? safeSelection.source_title;
  const issuer = source?.issuer_snapshot ?? safeSelection.source_issuer;
  const locator = source?.locator_snapshot ?? safeSelection.locator_snapshot;
  const evidence = source?.evidence_snapshot ?? safeSelection.evidence_snapshot;
  const url = safeExternalUrl(source?.url_snapshot ?? safeSelection.source_url);
  const statusCopy = detail
    ? SOURCE_STATUS_COPY[detail.current_source_status]
    : "Saved citation snapshot";
  const verificationStatus =
    detail?.verification_status ?? safeSelection.verification_status;

  return (
    <aside
      className="ask-citation-evidence-panel"
      role="complementary"
      aria-label="Citation evidence"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          onClose();
        }
      }}
    >
      <header className="ask-citation-evidence-header">
        <div>
          <span className="ask-citation-evidence-kicker">
            Official Regulatory Corpus
          </span>
          <h2>{title}</h2>
          <span
            className="ask-citation-source-status"
            data-source-status={detail?.current_source_status ?? "saved"}
          >
            {statusCopy}
          </span>
        </div>
        <button
          ref={closeButtonRef}
          type="button"
          className="ask-citation-close"
          aria-label="Close evidence panel"
          onClick={onClose}
        >
          ×
        </button>
      </header>

      <div className="ask-citation-load-state" aria-live="polite">
        {loadState === "loading"
          ? "Checking current source status…"
          : null}
        {loadState === "error"
          ? "Current source details could not be loaded. The saved citation snapshot remains available."
          : null}
      </div>

      <section className="ask-citation-claim" aria-labelledby={claimTitleId}>
        <h3 id={claimTitleId}>Related claim</h3>
        <p>{detail?.claim_text ?? safeSelection.claim_text}</p>
        <dl className="ask-citation-metadata ask-citation-support">
          <div>
            <dt>Verification</dt>
            <dd>{verificationCopy(verificationStatus)}</dd>
          </div>
          <div>
            <dt>Support score</dt>
            <dd>{supportScoreCopy(detail?.support_score ?? safeSelection.support_score)}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby={sourceTitleId}>
        <h3 id={sourceTitleId}>Source metadata</h3>
        <dl className="ask-citation-metadata">
          <div>
            <dt>Issuer</dt>
            <dd>{issuer ?? "Not established"}</dd>
          </div>
          <div>
            <dt>Source type</dt>
            <dd>{source?.source_type ?? safeSelection.source_type}</dd>
          </div>
          <div>
            <dt>Published</dt>
            <dd>{formatTimestamp(source?.published_at ?? safeSelection.published_at)}</dd>
          </div>
          <div>
            <dt>Retrieved</dt>
            <dd>{formatTimestamp(source?.retrieved_at ?? safeSelection.retrieved_at)}</dd>
          </div>
          <div>
            <dt>Cited section / page</dt>
            <dd>{locator ?? "Not established"}</dd>
          </div>
        </dl>
      </section>

      <section aria-labelledby={excerptTitleId}>
        <h3 id={excerptTitleId}>Stored evidence excerpt</h3>
        <blockquote>{evidence}</blockquote>
      </section>

      <footer className="ask-citation-evidence-actions">
        {url ? (
          <a href={url} target="_blank" rel="noreferrer">
            Open official source
          </a>
        ) : (
          <span className="ask-citation-link-unavailable">
            Source link unavailable
          </span>
        )}
        {onSaveCitation ? (
          <button
            type="button"
            onClick={() => onSaveCitation(safeSelection)}
          >
            Pin citation
          </button>
        ) : null}
      </footer>
    </aside>
  );
}

function assertDetailMatchesSelection(
  detail: AskCitationDetail,
  selection: AskCitationSelection,
) {
  if (
    detail.message_id !== selection.message_id ||
    detail.response_version !== selection.response_version ||
    detail.citation_id !== selection.citation_id ||
    detail.claim_id !== selection.claim_id ||
    detail.source.id !== selection.source_id
  ) {
    throw new Error("Citation detail identity does not match the selection");
  }
}

function verificationCopy(value: string) {
  return VERIFICATION_COPY[value] ?? "Unavailable";
}

function supportScoreCopy(value: number | null) {
  return value === null ? "Not established" : `${Math.round(value * 100)}%`;
}

function formatTimestamp(value: string | null) {
  if (value === null) return "Not established";
  const timestamp = new Date(value);
  if (Number.isNaN(timestamp.getTime())) return "Not established";
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(timestamp);
}

function safeExternalUrl(value: string) {
  try {
    const parsed = new URL(value);
    return parsed.protocol === "https:" ? parsed.toString() : null;
  } catch {
    return null;
  }
}
