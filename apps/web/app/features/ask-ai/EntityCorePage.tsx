"use client";

import { useId } from "react";

import {
  askEntityCorePageSchema,
  type AskEntityCorePage,
} from "@/lib/ask-ai-entity-page";
import type { AskStructuredResponseSection } from "@/lib/ask-ai-response";

import {
  CoreResponseCard,
  type CoreCardActionHandlers,
} from "./CoreCards";

const MODE_COPY = {
  grounded_regulatory: "Official Regulatory Corpus",
  general_ai: "General AI Knowledge",
  live_intelligence: "Live Web Sources",
} as const;

const EMPTY_STATE_COPY = {
  empty_by_evidence: "Not established from the available evidence.",
  omitted: "Not established for this response.",
  needs_clarification:
    "Not established until the required scope is clarified.",
  cancelled: "Unavailable because this section was cancelled.",
} as const;

export function EntityCorePage({
  canonicalEntityId,
  page: rawPage,
  actionHandlers = {},
}: {
  canonicalEntityId: string;
  page: unknown;
  actionHandlers?: CoreCardActionHandlers;
}) {
  const parsed = askEntityCorePageSchema.safeParse(rawPage);
  if (
    !parsed.success ||
    parsed.data.canonical_id !== canonicalEntityId
  ) {
    return (
      <section className="entity-core-page-error" role="alert">
        <h3>Core entity sections are unavailable</h3>
        <p>
          The page data did not match the selected canonical entity. No
          unverified content was shown.
        </p>
      </section>
    );
  }
  const page: AskEntityCorePage = parsed.data;
  return (
    <div
      className="entity-core-page"
      data-entity-id={page.canonical_id}
      data-response-id={page.response.response_id}
    >
      {page.response.sections.map((section) => (
        <EntityCoreSection
          key={section.section_id}
          section={section}
          actionHandlers={actionHandlers}
        />
      ))}
    </div>
  );
}

function EntityCoreSection({
  section,
  actionHandlers,
}: {
  section: AskStructuredResponseSection;
  actionHandlers: CoreCardActionHandlers;
}) {
  const titleId = `entity-core-${useId().replaceAll(":", "")}`;
  const degradedWithoutContent =
    section.state === "degraded" && section.cards.length === 0;
  const emptyCopy =
    section.state in EMPTY_STATE_COPY
      ? EMPTY_STATE_COPY[
          section.state as keyof typeof EMPTY_STATE_COPY
        ]
      : null;
  return (
    <section
      className="entity-core-section"
      data-section-key={section.section_key}
      data-section-state={section.state}
      data-mode={section.knowledge_mode}
      aria-labelledby={titleId}
    >
      <header>
        <div>
          <p className="entity-core-mode">
            Knowledge mode: {MODE_COPY[section.knowledge_mode]}
          </p>
          <h3 id={titleId}>{section.title}</h3>
        </div>
        <span>{readableState(section.state)}</span>
      </header>
      {section.state === "degraded" && section.cards.length > 0 ? (
        <p className="entity-core-notice" role="status">
          Partial section — verified content remains visible while missing
          material stays explicit.
        </p>
      ) : null}
      {degradedWithoutContent ? (
        <p className="entity-core-notice" role="status">
          Unavailable — this section could not establish verified content.
        </p>
      ) : null}
      {emptyCopy !== null ? (
        <p className="entity-core-notice" role="status">
          {emptyCopy}
        </p>
      ) : null}
      {section.cards.map((card) => (
        <CoreResponseCard
          key={card.card_id}
          card={card}
          actionHandlers={actionHandlers}
        />
      ))}
      {section.assumptions.length > 0 ? (
        <EntitySectionList
          title="Assumptions"
          items={section.assumptions}
        />
      ) : null}
      {section.gaps.length > 0 ? (
        <EntitySectionList title="Evidence gaps" items={section.gaps} />
      ) : null}
    </section>
  );
}

function EntitySectionList({
  title,
  items,
}: {
  title: string;
  items: string[];
}) {
  return (
    <aside className="entity-core-metadata" aria-label={title}>
      <h4>{title}</h4>
      <ul>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </aside>
  );
}

function readableState(value: AskStructuredResponseSection["state"]) {
  return value
    .split("_")
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}
