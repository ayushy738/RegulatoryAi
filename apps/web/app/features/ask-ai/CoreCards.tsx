"use client";

import { useId } from "react";

import {
  askAnswerSummaryPayloadSchema,
  askConfidenceCoveragePayloadSchema,
  askDefinitionPayloadSchema,
  askOfficialSourcePayloadSchema,
  type AskStructuredDateField,
  type AskStructuredTextField,
} from "../../../lib/ask-ai-core-cards";
import {
  askResponseCardSchema,
  type AskCardAction,
  type AskResponseCard,
} from "../../../lib/ask-ai-response";

type CoreCardType =
  | "answer_summary"
  | "definition"
  | "official_source"
  | "confidence_coverage";

export type CoreCardActionHandler = (
  target: string,
  card: AskResponseCard,
) => void;

export type CoreCardActionHandlers = Partial<
  Record<AskCardAction["action"], CoreCardActionHandler>
>;

const MODE_COPY = {
  grounded_regulatory: "Official Regulatory Corpus",
  general_ai: "General AI Knowledge",
  live_intelligence: "Live Web Sources",
} as const;

const STATE_COPY = {
  ready: "Ready",
  partial: "Partial — some fields are not established",
  not_established: "Not established",
  unavailable: "Unavailable",
} as const;

const ACTION_COPY: Record<AskCardAction["action"], string> = {
  inspect_evidence: "Inspect evidence",
  open_source: "Open",
  save: "Save",
  add_to_workspace: "Add to workspace",
  compare: "Compare",
  open_entity: "Open entity",
  ask_follow_up: "Ask follow-up",
  find_official_basis: "Find official basis",
  check_applicability: "Check applicability",
  add_to_tracker: "Add to tracker",
};

const SOURCE_STATUS_COPY = {
  draft: "Draft",
  consultation: "Consultation",
  in_force: "In force",
  superseded: "Superseded",
  repealed: "Repealed",
  unknown: "Unknown",
} as const;

function TextValue({ field }: { field: AskStructuredTextField }) {
  return (
    <span data-field-state={field.state}>
      {field.state === "established" ? field.value : "Not established"}
    </span>
  );
}

function DateValue({ field }: { field: AskStructuredDateField }) {
  return (
    <time
      dateTime={field.state === "established" ? field.value ?? undefined : undefined}
      data-field-state={field.state}
    >
      {field.state === "established" ? field.value : "Not established"}
    </time>
  );
}

function Metadata({
  entries,
}: {
  entries: readonly { label: string; value: React.ReactNode }[];
}) {
  return (
    <dl className="ask-core-card-metadata">
      {entries.map((entry) => (
        <div key={entry.label}>
          <dt>{entry.label}</dt>
          <dd>{entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CardActions({
  card,
  handlers,
}: {
  card: AskResponseCard;
  handlers: CoreCardActionHandlers;
}) {
  const generatedId = useId().replaceAll(":", "");
  const visible = card.actions.filter(
    (action) => action.state === "disabled" || handlers[action.action],
  );
  if (visible.length === 0) return null;

  return (
    <div
      className="ask-core-card-actions"
      role="group"
      aria-label={`${card.title} actions`}
    >
      {visible.map((action, index) => {
        const label = ACTION_COPY[action.action];
        if (action.state === "disabled") {
          const reasonId = `ask-core-action-${generatedId}-${index}`;
          return (
            <span className="ask-core-card-disabled-action" key={action.action}>
              <button type="button" disabled aria-describedby={reasonId}>
                {label}
              </button>
              <span id={reasonId}>
                Unavailable — this behavior is not enabled.
              </span>
            </span>
          );
        }
        const handler = handlers[action.action];
        if (!handler || action.target === null) return null;
        return (
          <button
            type="button"
            key={action.action}
            onClick={() => handler(action.target as string, card)}
          >
            {label}
          </button>
        );
      })}
    </div>
  );
}

function AnswerSummary({ card }: { card: AskResponseCard }) {
  const payload = askAnswerSummaryPayloadSchema.parse(card.payload);
  return (
    <>
      <p className="ask-core-card-answer">{payload.direct_answer}</p>
      <div className="ask-core-card-section">
        <h4>Why it matters</h4>
        <p>
          <TextValue field={payload.why_it_matters} />
        </p>
      </div>
      {payload.unresolved_assumptions.length ? (
        <div className="ask-core-card-section">
          <h4>Unresolved assumptions</h4>
          <ul>
            {payload.unresolved_assumptions.map((assumption) => (
              <li key={assumption}>{assumption}</li>
            ))}
          </ul>
        </div>
      ) : null}
      <p className="ask-core-card-source-count">
        {payload.source_count} {payload.source_count === 1 ? "source" : "sources"}
      </p>
    </>
  );
}

function Definition({ card }: { card: AskResponseCard }) {
  const payload = askDefinitionPayloadSchema.parse(card.payload);
  return (
    <>
      <p className="ask-core-card-kicker">{payload.term}</p>
      <Metadata
        entries={[
          {
            label: "Official definition",
            value: <TextValue field={payload.official_definition} />,
          },
          {
            label: "Acronym expansion",
            value: <TextValue field={payload.acronym_expansion} />,
          },
          {
            label: "Common confusion",
            value: <TextValue field={payload.common_confusion} />,
          },
          {
            label: "Official source",
            value: <TextValue field={payload.official_source_label} />,
          },
        ]}
      />
      <div className="ask-core-card-section">
        <h4>Plain-language explanation</h4>
        <p>{payload.plain_language_explanation}</p>
      </div>
    </>
  );
}

function OfficialSource({ card }: { card: AskResponseCard }) {
  const payload = askOfficialSourcePayloadSchema.parse(card.payload);
  return (
    <>
      <p className="ask-core-card-answer">{payload.document_title}</p>
      <Metadata
        entries={[
          { label: "Issuer / regulator", value: payload.issuer },
          { label: "Document type", value: payload.document_type },
          {
            label: "Issue date",
            value: <DateValue field={payload.issue_date} />,
          },
          {
            label: "Effective date",
            value: <DateValue field={payload.effective_date} />,
          },
          {
            label: "Current status",
            value: SOURCE_STATUS_COPY[payload.current_status],
          },
          { label: "Cited section / page", value: payload.cited_locator },
          { label: "Relationship", value: payload.relationship },
        ]}
      />
      <blockquote className="ask-core-card-excerpt">
        <span>Evidence excerpt</span>
        {payload.excerpt}
      </blockquote>
    </>
  );
}

function ConfidenceCoverageCard({ card }: { card: AskResponseCard }) {
  const payload = askConfidenceCoveragePayloadSchema.parse(card.payload);
  const confidence = card.confidence;
  if (confidence === null) {
    throw new Error("Confidence and Coverage Card requires confidence");
  }
  return (
    <>
      <p className="ask-core-card-confidence-label">
        {confidence.label} confidence · {confidence.score.toFixed(1)} out of 100
      </p>
      <div
        className="ask-core-card-meter"
        role="meter"
        aria-label={`${card.title} evidence coverage`}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={payload.coverage_percent}
        aria-valuetext={`${payload.coverage_percent.toFixed(1)} out of 100`}
      >
        <span style={{ width: `${payload.coverage_percent}%` }} />
      </div>
      <p className="ask-core-card-trust-note">
        Evidence confidence is not a probability of legal correctness.
      </p>
      <Metadata
        entries={[
          {
            label: "Modes used",
            value: payload.modes_used.map((mode) => MODE_COPY[mode]).join(", "),
          },
          {
            label: "Official documents found",
            value: payload.official_documents_found,
          },
          { label: "Live sources found", value: payload.live_sources_found },
          {
            label: "Corpus freshness",
            value: <TextValue field={payload.corpus_freshness} />,
          },
        ]}
      />
      <div className="ask-core-card-section">
        <h4>Why this confidence is shown</h4>
        <ul className="ask-core-card-reasons">
          {payload.reasons.map((reason) => (
            <li key={`${reason.kind}:${reason.text}`}>
              <span>{reason.kind}</span>
              {reason.text}
            </li>
          ))}
        </ul>
      </div>
      {payload.unsupported_or_inferred_areas.length ? (
        <div className="ask-core-card-section">
          <h4>Unsupported or inferred areas</h4>
          <ul>
            {payload.unsupported_or_inferred_areas.map((area) => (
              <li key={area}>{area}</li>
            ))}
          </ul>
        </div>
      ) : null}
      {payload.what_would_improve_confidence.length ? (
        <div className="ask-core-card-section">
          <h4>What would improve confidence</h4>
          <ul>
            {payload.what_would_improve_confidence.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      ) : null}
    </>
  );
}

function isCoreCard(card: AskResponseCard): card is AskResponseCard & {
  card_type: CoreCardType;
} {
  return [
    "answer_summary",
    "definition",
    "official_source",
    "confidence_coverage",
  ].includes(card.card_type);
}

export function CoreResponseCard({
  card: rawCard,
  actionHandlers = {},
}: {
  card: unknown;
  actionHandlers?: CoreCardActionHandlers;
}) {
  const card = askResponseCardSchema.parse(rawCard);
  if (!isCoreCard(card)) {
    throw new Error("CoreResponseCard supports only E8.2 card types");
  }
  const generatedId = useId().replaceAll(":", "");
  const titleId = `ask-core-card-${generatedId}`;

  return (
    <article
      className="ask-core-card"
      data-card-type={card.card_type}
      data-mode={card.knowledge_mode}
      data-state={card.state}
      aria-labelledby={titleId}
    >
      <header className="ask-core-card-header">
        <div>
          <p>{MODE_COPY[card.knowledge_mode]}</p>
          <h3 id={titleId}>{card.title}</h3>
        </div>
        <span>{STATE_COPY[card.state]}</span>
      </header>
      {card.card_type === "answer_summary" ? (
        <AnswerSummary card={card} />
      ) : null}
      {card.card_type === "definition" ? <Definition card={card} /> : null}
      {card.card_type === "official_source" ? (
        <OfficialSource card={card} />
      ) : null}
      {card.card_type === "confidence_coverage" ? (
        <ConfidenceCoverageCard card={card} />
      ) : null}
      <CardActions card={card} handlers={actionHandlers} />
    </article>
  );
}
