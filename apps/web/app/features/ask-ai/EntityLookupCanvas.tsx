"use client";

import { ArrowRight, BadgeCheck } from "lucide-react";
import { useId } from "react";

import type {
  AskEntityLookupCandidate,
  AskEntityLookupResponse,
} from "@/lib/ask-ai-entities";

import { EntityCorePage } from "./EntityCorePage";

export function EntityLookupCanvas({
  result,
  corePage = null,
  error = null,
  selecting = false,
  onChoose,
}: {
  result: AskEntityLookupResponse | null;
  corePage?: unknown | null;
  error?: string | null;
  selecting?: boolean;
  onChoose: (candidate: AskEntityLookupCandidate) => void;
}) {
  const generatedId = useId().replaceAll(":", "");
  if (error !== null) {
    return (
      <section className="entity-no-match" role="alert">
        <p className="entity-surface-label">Entity lookup unavailable</p>
        <h2>Entity lookup could not be completed</h2>
        <p>{error}</p>
      </section>
    );
  }
  if (result === null) {
    return (
      <div className="research-workspace-empty-canvas" role="status">
        <h2>Start with a regulatory question</h2>
        <p>
          Type a regulatory entity or acronym to open its Intelligence Page.
        </p>
      </div>
    );
  }
  if (result.status === "resolved" && result.selected !== null) {
    return (
      <div className="entity-intelligence-page">
        <EntityIntelligenceHeader
          mention={result.mention}
          entity={result.selected}
        />
        {corePage === null ? (
          <p className="entity-section-boundary" role="status">
            Verified core sections are not available for this entity yet.
          </p>
        ) : (
          <EntityCorePage
            canonicalEntityId={result.selected.canonical_id}
            page={corePage}
          />
        )}
      </div>
    );
  }
  if (result.status === "ambiguous") {
    const titleId = `entity-selector-title-${generatedId}`;
    return (
      <section
        className="entity-disambiguation"
        aria-labelledby={titleId}
      >
        <p className="entity-surface-label">Entity clarification</p>
        <h2 id={titleId}>Choose the regulatory entity</h2>
        <p>{result.clarification_question}</p>
        <ul>
          {result.candidates.map((candidate) => (
            <li key={candidate.canonical_id}>
              <button
                type="button"
                disabled={selecting}
                onClick={() => onChoose(candidate)}
              >
                <span>
                  <strong>{candidate.canonical_name}</strong>
                  <small>
                    {candidate.jurisdiction} ·{" "}
                    {readableEntityClass(candidate.entity_class)}
                  </small>
                  <small>{candidate.match_reason}</small>
                </span>
                <ArrowRight size={18} aria-hidden="true" />
              </button>
            </li>
          ))}
        </ul>
        <p role="status">
          {selecting
            ? "Opening the selected entity…"
            : "Selection is required before entity research begins."}
        </p>
      </section>
    );
  }
  return (
    <section className="entity-no-match" role="status">
      <p className="entity-surface-label">Entity lookup</p>
      <h2>No canonical entity matched</h2>
      <p>{result.clarification_question}</p>
      <p>Try the full regulatory name or add a jurisdiction.</p>
    </section>
  );
}

function EntityIntelligenceHeader({
  mention,
  entity,
}: {
  mention: string;
  entity: AskEntityLookupCandidate;
}) {
  const titleId = `entity-intelligence-${useId().replaceAll(":", "")}`;
  const visibleAliases = entity.aliases.filter(
    (alias) =>
      alias.localeCompare(entity.canonical_name, undefined, {
        sensitivity: "accent",
      }) !== 0,
  );
  const showsExpansion =
    mention.localeCompare(entity.canonical_name, undefined, {
      sensitivity: "accent",
    }) !== 0;
  return (
    <article
      className="entity-intelligence-header"
      data-surface="entity_intelligence_page"
      aria-labelledby={titleId}
    >
      <div>
        <p className="entity-surface-label">
          <BadgeCheck size={16} aria-hidden="true" />
          Entity Intelligence Page
        </p>
        <h2 id={titleId}>{entity.canonical_name}</h2>
        {showsExpansion ? (
          <p className="entity-expansion">
            <strong>{mention}</strong> maps to {entity.canonical_name}.
          </p>
        ) : null}
      </div>
      <dl>
        <div>
          <dt>Jurisdiction</dt>
          <dd>{entity.jurisdiction}</dd>
        </div>
        <div>
          <dt>Entity type</dt>
          <dd>{readableEntityClass(entity.entity_class)}</dd>
        </div>
        <div>
          <dt>Resolution confidence</dt>
          <dd>{Math.round(entity.confidence * 100)}%</dd>
        </div>
      </dl>
      {visibleAliases.length > 0 ? (
        <section aria-label="Known aliases">
          <h3>Known aliases</h3>
          <ul>
            {visibleAliases.map((alias) => (
              <li key={alias}>{alias}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <p className="entity-match-reason">{entity.match_reason}</p>
    </article>
  );
}

function readableEntityClass(value: string) {
  return value
    .split("_")
    .map((part) => `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`)
    .join(" ");
}
