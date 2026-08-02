"use client";

import type { ReactNode } from "react";

import {
  askDeadlinePayloadSchema,
  askObligationPayloadSchema,
  askStakeholderPayloadSchema,
  type AskCardEvidenceReference,
} from "../../../lib/ask-ai-compliance-cards";
import {
  askResponseCardSchema,
  type AskCardAction,
  type AskResponseCard,
} from "../../../lib/ask-ai-response";
import type { AskStructuredTextField } from "../../../lib/ask-ai-core-cards";

type ComplianceCardType = "obligation" | "deadline" | "stakeholder";

export type ComplianceCardActionHandler = (
  target: string,
  card: AskResponseCard,
) => void;

export type ComplianceCardActionHandlers = Partial<
  Record<AskCardAction["action"], ComplianceCardActionHandler>
>;

const STATE_COPY = {
  ready: "Ready",
  partial: "Partial — some fields are not established",
  not_established: "Not established",
  unavailable: "Unavailable",
} as const;

const DEADLINE_STATUS_COPY = {
  upcoming: "Upcoming",
  today: "Today",
  elapsed: "Elapsed",
  extended: "Extended",
  unverified: "Unverified",
} as const;

const ACTION_COPY: Partial<Record<AskCardAction["action"], string>> = {
  check_applicability: "Check applicability",
  open_entity: "Open stakeholder",
  add_to_tracker: "Add to tracker",
};

function TextValue({ field }: { field: AskStructuredTextField }) {
  return (
    <span data-field-state={field.state}>
      {field.state === "established" ? field.value : "Not established"}
    </span>
  );
}

function Metadata({
  entries,
}: {
  entries: readonly { label: string; value: ReactNode }[];
}) {
  return (
    <dl className="ask-compliance-card-metadata">
      {entries.map((entry) => (
        <div key={entry.label}>
          <dt>{entry.label}</dt>
          <dd>{entry.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function EvidenceReferences({
  references,
  card,
  handler,
}: {
  references: AskCardEvidenceReference[];
  card: AskResponseCard;
  handler?: ComplianceCardActionHandler;
}) {
  if (references.length === 0) {
    return <p className="ask-compliance-no-evidence">Official basis not established.</p>;
  }
  return (
    <div className="ask-compliance-references" aria-label="Official evidence">
      {references.map((reference) =>
        handler ? (
          <button
            type="button"
            key={reference.citation_id}
            aria-label={`Inspect citation ${reference.marker}`}
            onClick={() => handler(reference.citation_id, card)}
          >
            {reference.marker} {reference.locator.value ?? "Official evidence"}
          </button>
        ) : (
          <span key={reference.citation_id}>
            {reference.marker} {reference.locator.value ?? "Official evidence"}
          </span>
        ),
      )}
    </div>
  );
}

function SecondaryActions({
  card,
  handlers,
}: {
  card: AskResponseCard;
  handlers: ComplianceCardActionHandlers;
}) {
  const actions = card.actions.filter((action) => action.action !== "inspect_evidence");
  if (actions.length === 0) return null;
  return (
    <div className="ask-compliance-actions" role="group" aria-label={`${card.title} actions`}>
      {actions.map((action) => {
        const label = ACTION_COPY[action.action];
        if (!label) return null;
        if (action.state === "disabled") {
          return (
            <button type="button" key={action.action} disabled>
              {label} — unavailable
            </button>
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

function Obligation({ card }: { card: AskResponseCard }) {
  const payload = askObligationPayloadSchema.parse(card.payload);
  return (
    <Metadata
      entries={[
        { label: "Responsible party", value: <TextValue field={payload.responsible_party} /> },
        { label: "Required action", value: <TextValue field={payload.required_action} /> },
        { label: "When / frequency", value: <TextValue field={payload.timing_or_frequency} /> },
        { label: "Trigger / scope", value: <TextValue field={payload.trigger_or_scope} /> },
        { label: "Jurisdiction", value: <TextValue field={payload.jurisdiction} /> },
        { label: "Official basis", value: <TextValue field={payload.official_basis} /> },
      ]}
    />
  );
}

function Deadline({ card }: { card: AskResponseCard }) {
  const payload = askDeadlinePayloadSchema.parse(card.payload);
  return (
    <Metadata
      entries={[
        {
          label: "Date",
          value: payload.date.state === "established" ? (
            <time dateTime={payload.date.value ?? undefined}>{payload.date.value}</time>
          ) : (
            <span data-field-state="not_established">Not established</span>
          ),
        },
        { label: "Deadline type", value: <TextValue field={payload.deadline_type} /> },
        { label: "Responsible stakeholder", value: <TextValue field={payload.responsible_stakeholder} /> },
        { label: "Status", value: DEADLINE_STATUS_COPY[payload.status] },
        { label: "Official source", value: <TextValue field={payload.source_label} /> },
      ]}
    />
  );
}

function Stakeholder({ card }: { card: AskResponseCard }) {
  const payload = askStakeholderPayloadSchema.parse(card.payload);
  return (
    <>
      <Metadata
        entries={[
          { label: "Stakeholder", value: <TextValue field={payload.stakeholder} /> },
          { label: "Role", value: <TextValue field={payload.role} /> },
          { label: "Impact", value: <TextValue field={payload.impact} /> },
          { label: "Jurisdiction", value: <TextValue field={payload.jurisdiction} /> },
        ]}
      />
      <div className="ask-compliance-list">
        <h4>Relevant obligations</h4>
        {payload.obligations.length ? (
          <ul>{payload.obligations.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : <p>Not established</p>}
      </div>
      <div className="ask-compliance-list">
        <h4>Relevant regulations</h4>
        {payload.relevant_regulations.length ? (
          <ul>{payload.relevant_regulations.map((item) => <li key={item}>{item}</li>)}</ul>
        ) : <p>Not established</p>}
      </div>
      <div
        className="ask-compliance-coverage"
        role="meter"
        aria-label="Stakeholder evidence coverage"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={payload.evidence_coverage_percent}
      >
        <span style={{ width: `${payload.evidence_coverage_percent}%` }} />
      </div>
      <p>{payload.evidence_coverage_percent}% evidence coverage</p>
    </>
  );
}

export function ComplianceResponseCard({
  card,
  actionHandlers = {},
}: {
  card: AskResponseCard | unknown;
  actionHandlers?: ComplianceCardActionHandlers;
}) {
  const parsed = askResponseCardSchema.parse(card);
  if (!["obligation", "deadline", "stakeholder"].includes(parsed.card_type)) {
    throw new Error("ComplianceResponseCard received an unsupported card type");
  }
  const cardType = parsed.card_type as ComplianceCardType;
  const references = {
    obligation: askObligationPayloadSchema,
    deadline: askDeadlinePayloadSchema,
    stakeholder: askStakeholderPayloadSchema,
  }[cardType].parse(parsed.payload).evidence_references;

  return (
    <article
      className="ask-compliance-card"
      aria-label={parsed.title}
      data-card-type={cardType}
      data-state={parsed.state}
    >
      <header>
        <div>
          <p>Official Regulatory Corpus</p>
          <h3>{parsed.title}</h3>
        </div>
        <span>{STATE_COPY[parsed.state]}</span>
      </header>
      {cardType === "obligation" ? <Obligation card={parsed} /> : null}
      {cardType === "deadline" ? <Deadline card={parsed} /> : null}
      {cardType === "stakeholder" ? <Stakeholder card={parsed} /> : null}
      <EvidenceReferences
        references={references}
        card={parsed}
        handler={actionHandlers.inspect_evidence}
      />
      {parsed.confidence ? (
        <p className="ask-compliance-confidence">
          {parsed.confidence.label} confidence · {parsed.confidence.score} out of 100
        </p>
      ) : null}
      <SecondaryActions card={parsed} handlers={actionHandlers} />
    </article>
  );
}
