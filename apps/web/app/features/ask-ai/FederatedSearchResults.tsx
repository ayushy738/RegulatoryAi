"use client";

import { ArrowRight, RotateCcw, Search } from "lucide-react";
import type { KeyboardEvent } from "react";

import type {
  AskFederatedSearchRequest,
  AskFederatedSearchResponse,
  AskSearchItem,
} from "@/lib/ask-ai-search";

const GROUP_COPY = {
  best_match: "Best Match",
  entities: "Entities",
  official_regulations: "Official Regulations",
  official_documents: "Official Documents",
  amendments: "Amendments",
  consultations: "Consultations",
  deadlines: "Deadlines",
  previous_research: "Previous Research",
} as const;

export function FederatedSearchResults({
  result,
  pending,
  error,
  onSelect,
  onRestoreOriginal,
  filters,
  onFiltersChange,
}: {
  result: AskFederatedSearchResponse | null;
  pending: boolean;
  error: string | null;
  onSelect: (item: AskSearchItem) => void;
  onRestoreOriginal: (query: string) => void;
  filters: AskFederatedSearchRequest["filters"];
  onFiltersChange: (
    filters: AskFederatedSearchRequest["filters"],
  ) => void;
}) {
  if (error !== null) {
    return (
      <section className="federated-search-error" role="alert">
        <h2>Research search is unavailable</h2>
        <p>{error}</p>
      </section>
    );
  }
  if (pending && result === null) {
    return (
      <p className="federated-search-status" role="status">
        Searching canonical research sources…
      </p>
    );
  }
  if (result === null) return null;
  const populated = result.groups.filter(
    (group) => group.status === "complete",
  );
  const unavailable = result.groups.filter(
    (group) => group.status === "unavailable",
  );
  return (
    <section className="federated-search-results" aria-label="Research search">
      <header>
        <div>
          <p>Federated research search</p>
          <h2>Results for “{result.original_query}”</h2>
        </div>
        {pending ? <span role="status">Refreshing…</span> : null}
      </header>
      {result.correction !== null ? (
        <div className="federated-search-correction" role="status">
          <Search size={17} aria-hidden="true" />
          <p>
            Interpreted as <strong>{result.applied_query}</strong>. Original
            query preserved as “{result.original_query}”.
          </p>
          <button
            type="button"
            onClick={() => onRestoreOriginal(result.original_query)}
          >
            <RotateCcw size={15} aria-hidden="true" />
            Search original
          </button>
        </div>
      ) : null}
      <div className="federated-search-filters" aria-label="Search filters">
        <label>
          Provenance
          <select
            value={filters.provenance ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                provenance:
                  (event.target.value as
                    | "internal_regulatory_corpus"
                    | "owned_research") || undefined,
              })
            }
          >
            <option value="">All provenance</option>
            <option value="internal_regulatory_corpus">
              Internal regulatory corpus
            </option>
            <option value="owned_research">Previous research</option>
          </select>
        </label>
        <label>
          Jurisdiction
          <input
            value={filters.jurisdiction ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                jurisdiction: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Regulator
          <input
            value={filters.regulator ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                regulator: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Document type
          <input
            value={filters.document_type ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                document_type: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Entity class
          <input
            value={filters.entity_class ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                entity_class: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Status
          <input
            value={filters.status ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                status: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Stakeholder
          <input
            value={filters.stakeholder ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                stakeholder: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Topic
          <input
            value={filters.topic ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                topic: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          Lifecycle
          <select
            value={filters.lifecycle ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                lifecycle:
                  (event.target.value as
                    | "current"
                    | "superseded"
                    | "draft") || undefined,
              })
            }
          >
            <option value="">All lifecycle states</option>
            <option value="current">Current</option>
            <option value="superseded">Superseded</option>
            <option value="draft">Draft</option>
          </select>
        </label>
        <label>
          From date
          <input
            type="date"
            value={filters.date_from ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                date_from: event.target.value || undefined,
              })
            }
          />
        </label>
        <label>
          To date
          <input
            type="date"
            value={filters.date_to ?? ""}
            onChange={(event) =>
              onFiltersChange({
                ...filters,
                date_to: event.target.value || undefined,
              })
            }
          />
        </label>
      </div>
      {unavailable.length > 0 ? (
        <p className="federated-search-status" role="status">
          Some result groups are temporarily unavailable:{" "}
          {unavailable
            .map((group) => GROUP_COPY[group.group])
            .join(", ")}.
        </p>
      ) : null}
      {populated.length === 0 ? (
        <p className="federated-search-status" role="status">
          No matching canonical research result was found
          {unavailable.length > 0 ? " in the available groups" : ""}.
        </p>
      ) : (
        <div
          className="federated-search-groups"
          role="listbox"
          aria-label="Research suggestions"
        >
          {populated.map((group) => (
            <section
              key={group.group}
              aria-labelledby={`search-group-${group.group}`}
            >
              <h3 id={`search-group-${group.group}`}>
                {GROUP_COPY[group.group]}
              </h3>
              {group.items.map((item) => (
                <button
                  key={`${group.group}:${item.result_id}`}
                  type="button"
                  role="option"
                  aria-selected="false"
                  data-search-option
                  onClick={() => onSelect(item)}
                  onKeyDown={moveOptionFocus}
                >
                  <span>
                    <strong>{item.title}</strong>
                    <small>{item.subtitle}</small>
                    <small>{item.why_matched}</small>
                  </span>
                  <ArrowRight size={17} aria-hidden="true" />
                </button>
              ))}
            </section>
          ))}
        </div>
      )}
    </section>
  );
}

function moveOptionFocus(event: KeyboardEvent<HTMLButtonElement>) {
  const { key } = event;
  if (!["ArrowDown", "ArrowUp", "Escape"].includes(key)) return;
  event.preventDefault();
  const options = Array.from(
    document.querySelectorAll<HTMLElement>("[data-search-option]"),
  );
  const current = options.indexOf(document.activeElement as HTMLElement);
  if (key === "Escape") {
    document
      .querySelector<HTMLTextAreaElement>(
        ".research-workspace-composer textarea",
      )
      ?.focus();
    return;
  }
  const delta = key === "ArrowDown" ? 1 : -1;
  options[(current + delta + options.length) % options.length]?.focus();
}
