"use client";

import {
  askAmendmentCardPayloadSchema,
  askComparisonCardPayloadSchema,
  askLiveNewsCardPayloadSchema,
  askRelatedRegulationCardPayloadSchema,
  askTimelineEventCardPayloadSchema,
  type AskLiveSourceReference,
} from "../../../lib/ask-ai-change-cards";
import type { AskCardEvidenceReference } from "../../../lib/ask-ai-compliance-cards";
import type { AskStructuredTextField } from "../../../lib/ask-ai-core-cards";
import {
  askResponseCardSchema,
  type AskCardAction,
  type AskResponseCard,
} from "../../../lib/ask-ai-response";

type ChangeCardType =
  | "timeline_event"
  | "amendment"
  | "comparison"
  | "live_news"
  | "related_regulation";

export type ChangeCardActionHandler = (target: string, card: AskResponseCard) => void;
export type ChangeCardActionHandlers = Partial<Record<AskCardAction["action"], ChangeCardActionHandler>>;

function TextValue({ field }: { field: AskStructuredTextField }) {
  return <span data-field-state={field.state}>{field.value ?? "Not established"}</span>;
}

function Evidence({ references, card, handler }: { references: AskCardEvidenceReference[]; card: AskResponseCard; handler?: ChangeCardActionHandler }) {
  return (
    <div className="ask-change-evidence" aria-label="Card evidence">
      {references.map((reference) =>
        handler ? (
          <button type="button" key={reference.citation_id} onClick={() => handler(reference.citation_id, card)} aria-label={`Inspect citation ${reference.marker}`}>
            {reference.marker} {reference.locator.value ?? "Official evidence"}
          </button>
        ) : (
          <span key={reference.citation_id}>{reference.marker} {reference.locator.value ?? "Official evidence"}</span>
        ),
      )}
    </div>
  );
}

function LiveSource({ source }: { source: AskLiveSourceReference }) {
  return (
    <section className="ask-change-live-source" aria-label="Live source">
      <span>{source.ui_badge}</span>
      <dl>
        <div><dt>Publisher</dt><dd>{source.publisher}</dd></div>
        <div><dt>Source type</dt><dd>{source.source_type}</dd></div>
        <div><dt>Published</dt><dd><time dateTime={source.publication_at}>{source.publication_at}</time></dd></div>
        <div><dt>Retrieved</dt><dd><time dateTime={source.retrieved_at}>{source.retrieved_at}</time></dd></div>
      </dl>
      <p>Attribution: {source.attribution}</p>
      <a href={source.url} target="_blank" rel="noreferrer">Open live source</a>
      <p>Live reporting does not establish official legal status.</p>
    </section>
  );
}

function Timeline({ card, handlers }: { card: AskResponseCard; handlers: ChangeCardActionHandlers }) {
  const payload = askTimelineEventCardPayloadSchema.parse(card.payload);
  return (
    <>
      <dl className="ask-change-metadata">
        <div><dt>Date</dt><dd><TextValue field={payload.date} /></dd></div>
        <div><dt>Event type</dt><dd><TextValue field={payload.event_type} /></dd></div>
        <div><dt>Event</dt><dd><TextValue field={payload.event_title} /></dd></div>
        <div><dt>Source</dt><dd><TextValue field={payload.source_label} /></dd></div>
      </dl>
      <section><h4>Change or significance</h4><p><TextValue field={payload.significance} /></p></section>
      <p className="ask-change-provenance">{payload.origin === "official" ? "Official Regulatory Corpus" : "Live Web Sources"}</p>
      {payload.related_prior_event_id ? <p>Prior event: {payload.related_prior_event_id}</p> : null}
      {payload.related_next_event_id ? <p>Next event: {payload.related_next_event_id}</p> : null}
      {payload.origin === "official" ? <Evidence references={payload.official_evidence_references} card={card} handler={handlers.inspect_evidence} /> : null}
      {payload.live_source ? <LiveSource source={payload.live_source} /> : null}
    </>
  );
}

function Amendment({ card, handlers }: { card: AskResponseCard; handlers: ChangeCardActionHandlers }) {
  const payload = askAmendmentCardPayloadSchema.parse(card.payload);
  return (
    <>
      <dl className="ask-change-metadata">
        <div><dt>Amending instrument</dt><dd><TextValue field={payload.amending_instrument} /></dd></div>
        <div><dt>Amended instrument</dt><dd><TextValue field={payload.amended_instrument} /></dd></div>
        <div><dt>Issue date</dt><dd><TextValue field={payload.issue_date} /></dd></div>
        <div><dt>Effective date</dt><dd><TextValue field={payload.effective_date} /></dd></div>
      </dl>
      <section><h4>Change summary</h4><p><TextValue field={payload.change_summary} /></p></section>
      <List title="Provisions affected" items={payload.provisions_affected} />
      <List title="Stakeholders affected" items={payload.stakeholders_affected} />
      <Evidence references={payload.evidence_references} card={card} handler={handlers.inspect_evidence} />
    </>
  );
}

function Comparison({ card, handlers }: { card: AskResponseCard; handlers: ChangeCardActionHandlers }) {
  const payload = askComparisonCardPayloadSchema.parse(card.payload);
  return (
    <div className="ask-change-comparison" role="table" aria-label={`${payload.side_a_label} and ${payload.side_b_label} comparison`}>
      <div role="row" className="ask-change-comparison-header"><span role="columnheader">Dimension</span><span role="columnheader">{payload.side_a_label}</span><span role="columnheader">{payload.side_b_label}</span><span role="columnheader">Difference</span></div>
      {payload.dimensions.map((dimension) => (
        <div role="row" key={dimension.dimension}>
          <strong role="rowheader">{dimension.dimension}</strong>
          <div role="cell"><TextValue field={dimension.side_a} /><Evidence references={dimension.side_a_evidence_references} card={card} handler={handlers.inspect_evidence} /></div>
          <div role="cell"><TextValue field={dimension.side_b} /><Evidence references={dimension.side_b_evidence_references} card={card} handler={handlers.inspect_evidence} /></div>
          <div role="cell"><TextValue field={dimension.relationship_or_difference} /></div>
        </div>
      ))}
    </div>
  );
}

function LiveNews({ card }: { card: AskResponseCard }) {
  const payload = askLiveNewsCardPayloadSchema.parse(card.payload);
  return <><h4 className="ask-change-headline">{payload.headline}</h4><p>{payload.relevance_explanation}</p><LiveSource source={payload.live_source} /></>;
}

function Related({ card, handlers }: { card: AskResponseCard; handlers: ChangeCardActionHandlers }) {
  const payload = askRelatedRegulationCardPayloadSchema.parse(card.payload);
  return (
    <>
      <dl className="ask-change-metadata">
        <div><dt>Related entity or document</dt><dd><TextValue field={payload.related_entity_or_document} /></dd></div>
        <div><dt>Relationship</dt><dd><TextValue field={payload.relationship_type} /></dd></div>
        <div><dt>Provenance</dt><dd><TextValue field={payload.provenance_label} /></dd></div>
      </dl>
      <section><h4>Explanation</h4><p><TextValue field={payload.explanation} /></p></section>
      <Evidence references={payload.evidence_references} card={card} handler={handlers.inspect_evidence} />
    </>
  );
}

function List({ title, items }: { title: string; items: string[] }) {
  return <section><h4>{title}</h4>{items.length ? <ul>{items.map((item) => <li key={item}>{item}</li>)}</ul> : <p data-field-state="not_established">Not established</p>}</section>;
}

const labels: Partial<Record<AskCardAction["action"], string>> = {
  compare: "Compare instruments",
  find_official_basis: "Find official basis",
  open_entity: "Open intelligence page",
};

function Actions({ card, handlers }: { card: AskResponseCard; handlers: ChangeCardActionHandlers }) {
  return (
    <div className="ask-change-actions">
      {card.actions.map((action) => {
        const label = labels[action.action];
        const handler = handlers[action.action];
        if (!label || action.state !== "available" || !action.target || !handler) return null;
        return <button type="button" key={action.action} onClick={() => handler(action.target as string, card)}>{label}</button>;
      })}
    </div>
  );
}

export function ChangeResponseCard({ card, actionHandlers = {} }: { card: AskResponseCard | unknown; actionHandlers?: ChangeCardActionHandlers }) {
  const parsed = askResponseCardSchema.parse(card);
  if (!["timeline_event", "amendment", "comparison", "live_news", "related_regulation"].includes(parsed.card_type)) throw new Error("ChangeResponseCard received an unsupported card type");
  const type = parsed.card_type as ChangeCardType;
  return (
    <article className="ask-change-card" aria-label={parsed.title} data-card-type={type} data-state={parsed.state} data-mode={parsed.knowledge_mode}>
      <header><div><p>{parsed.knowledge_mode === "live_intelligence" ? "Live Web Sources" : "Official Regulatory Corpus"}</p><h3>{parsed.title}</h3></div><span>{parsed.state === "partial" ? "Partial — gaps remain" : "Ready"}</span></header>
      {type === "timeline_event" ? <Timeline card={parsed} handlers={actionHandlers} /> : null}
      {type === "amendment" ? <Amendment card={parsed} handlers={actionHandlers} /> : null}
      {type === "comparison" ? <Comparison card={parsed} handlers={actionHandlers} /> : null}
      {type === "live_news" ? <LiveNews card={parsed} /> : null}
      {type === "related_regulation" ? <Related card={parsed} handlers={actionHandlers} /> : null}
      <p className="ask-change-confidence">{parsed.confidence?.label} confidence · {parsed.confidence?.score} out of 100</p>
      <Actions card={parsed} handlers={actionHandlers} />
    </article>
  );
}
