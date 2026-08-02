"use client";

import { useId, type ReactNode } from "react";

import {
  askStructuredResponseSchema,
  type AskCardAction,
  type AskResponseCard,
  type AskStructuredResponse,
  type AskStructuredResponseSection,
} from "../../../lib/ask-ai-response";

import { ChangeResponseCard } from "./ChangeCards";
import { ComplianceResponseCard } from "./ComplianceCards";
import { CoreResponseCard } from "./CoreCards";

export type StructuredCanvasActionHandler = (
  target: string,
  card: AskResponseCard,
) => void;

export type StructuredCanvasActionHandlers = Partial<
  Record<AskCardAction["action"], StructuredCanvasActionHandler>
>;

const MODE_COPY = {
  grounded_regulatory: {
    label: "Official Regulatory Corpus",
    disclosure: "Claims in this section are tied to internal official evidence.",
  },
  live_intelligence: {
    label: "Live Web Sources",
    disclosure:
      "Time-sensitive reporting is separate from official legal status.",
  },
  general_ai: {
    label: "General AI Knowledge",
    disclosure:
      "Educational context only; this section is not official regulatory evidence.",
  },
} as const;

const SECTION_STATE_COPY: Record<
  AskStructuredResponseSection["state"],
  string
> = {
  ready: "Ready",
  ready_without_synthesis: "Ready without synthesis",
  degraded: "Degraded",
  empty_by_evidence: "No evidence found",
  omitted: "Omitted",
  needs_clarification: "Needs clarification",
  cancelled: "Cancelled",
};

const CORE_CARD_TYPES = new Set([
  "answer_summary",
  "definition",
  "official_source",
  "confidence_coverage",
]);
const COMPLIANCE_CARD_TYPES = new Set([
  "obligation",
  "deadline",
  "stakeholder",
]);
const CHANGE_CARD_TYPES = new Set([
  "timeline_event",
  "amendment",
  "comparison",
  "live_news",
  "related_regulation",
]);
const INTROSPECTION_PATTERN =
  /\b(?:chain[- ]of[- ]thought|internal reasoning|hidden reasoning|model reasoning|system prompt|i think|i believe)\b/i;

function safeConfidenceReasons(reasons: readonly string[]) {
  return reasons.filter((reason) => !INTROSPECTION_PATTERN.test(reason));
}

function ConfidenceMeter({
  label,
  score,
}: {
  label: string;
  score: number;
}) {
  return (
    <div className="ask-structured-confidence">
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={score}
        aria-valuetext={`${score.toFixed(1)} out of 100`}
      >
        <span style={{ width: `${score}%` }} />
      </div>
      <span>{score.toFixed(1)} / 100</span>
    </div>
  );
}

function DetailList({
  title,
  items,
}: {
  title: string;
  items: readonly string[];
}) {
  if (items.length === 0) return null;
  return (
    <section className="ask-structured-detail-list">
      <h3>{title}</h3>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

function UnknownCard({ card }: { card: AskResponseCard }) {
  const generatedId = useId().replaceAll(":", "");
  const titleId = `ask-unknown-card-${generatedId}`;
  return (
    <article
      className="ask-structured-unknown-card"
      data-card-type={card.card_type}
      data-state={card.state}
      aria-labelledby={titleId}
    >
      <p>Unsupported card type</p>
      <h3 id={titleId}>{card.fallback_title ?? card.title}</h3>
      <span>{card.title}</span>
      <p>
        This card is not available in this workspace version. Its stored data
        remains preserved for a compatible renderer.
      </p>
    </article>
  );
}

function renderCard(
  card: AskResponseCard,
  actionHandlers: StructuredCanvasActionHandlers,
): ReactNode {
  if (CORE_CARD_TYPES.has(card.card_type)) {
    return (
      <CoreResponseCard
        key={card.card_id}
        card={card}
        actionHandlers={actionHandlers}
      />
    );
  }
  if (COMPLIANCE_CARD_TYPES.has(card.card_type)) {
    return (
      <ComplianceResponseCard
        key={card.card_id}
        card={card}
        actionHandlers={actionHandlers}
      />
    );
  }
  if (CHANGE_CARD_TYPES.has(card.card_type)) {
    return (
      <ChangeResponseCard
        key={card.card_id}
        card={card}
        actionHandlers={actionHandlers}
      />
    );
  }
  return <UnknownCard key={card.card_id} card={card} />;
}

function StructuredSection({
  section,
  actionHandlers,
}: {
  section: AskStructuredResponseSection;
  actionHandlers: StructuredCanvasActionHandlers;
}) {
  const generatedId = useId().replaceAll(":", "");
  const titleId = `ask-structured-section-${generatedId}`;
  const mode = MODE_COPY[section.knowledge_mode];
  const confidenceReasons = safeConfidenceReasons(section.confidence.reasons);
  return (
    <article
      className="ask-structured-section"
      data-mode={section.knowledge_mode}
      data-state={section.state}
      aria-labelledby={titleId}
    >
      <header className="ask-structured-section-header">
        <div>
          <p>{mode.label}</p>
          <h2 id={titleId}>{section.title}</h2>
          <span>{mode.disclosure}</span>
        </div>
        <div className="ask-structured-section-status">
          <strong>{SECTION_STATE_COPY[section.state]}</strong>
          <span>{section.strategy.replaceAll("_", " ")}</span>
        </div>
      </header>
      <ConfidenceMeter
        label={`${section.title} confidence`}
        score={section.confidence.score}
      />
      {confidenceReasons.length ? (
        <ul className="ask-structured-confidence-reasons">
          {confidenceReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      <DetailList title="Section assumptions" items={section.assumptions} />
      <DetailList title="Section gaps" items={section.gaps} />
      {section.cards.length ? (
        <div className="ask-structured-card-list">
          {section.cards.map((card) => renderCard(card, actionHandlers))}
        </div>
      ) : (
        <p className="ask-structured-empty-section" role="status">
          No structured cards are available for this section. The section state
          above remains authoritative.
        </p>
      )}
    </article>
  );
}

export function StructuredResponseCanvas({
  response: rawResponse,
  actionHandlers = {},
}: {
  response: AskStructuredResponse | unknown;
  actionHandlers?: StructuredCanvasActionHandlers;
}) {
  const response = askStructuredResponseSchema.parse(rawResponse);
  const confidenceReasons = safeConfidenceReasons(
    response.overall_confidence.reasons,
  );
  const generatedId = useId().replaceAll(":", "");
  const titleId = `ask-structured-response-${generatedId}`;
  return (
    <section
      className="ask-structured-response"
      aria-labelledby={titleId}
      data-response-strategy={response.response_strategy}
    >
      <header className="ask-structured-response-header">
        <div>
          <p>Structured regulatory response</p>
          <h2 id={titleId}>{response.compatibility_summary}</h2>
          <span>{response.response_strategy.replaceAll("_", " ")}</span>
        </div>
        <div>
          <strong>{response.overall_confidence.label} confidence</strong>
          <ConfidenceMeter
            label="Overall response confidence"
            score={response.overall_confidence.score}
          />
        </div>
      </header>
      {confidenceReasons.length ? (
        <ul className="ask-structured-confidence-reasons">
          {confidenceReasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : null}
      <div className="ask-structured-response-details">
        <DetailList title="Response assumptions" items={response.assumptions} />
        <DetailList title="Response gaps" items={response.gaps} />
      </div>
      <div className="ask-structured-section-list">
        {response.sections.map((section) => (
          <StructuredSection
            key={section.section_id}
            section={section}
            actionHandlers={actionHandlers}
          />
        ))}
      </div>
    </section>
  );
}
