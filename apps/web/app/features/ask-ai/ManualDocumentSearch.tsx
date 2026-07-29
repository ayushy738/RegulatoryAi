"use client";

import { ExternalLink, FileSearch, RotateCcw, Search } from "lucide-react";
import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { useManualDocumentSearch } from "@/lib/ask-ai-data";
import type {
  AskManualDocumentSearchItem,
  AskManualDocumentSearchRequest,
  AskManualDocumentSearchResponse,
} from "@/lib/ask-ai-manual-search";

type ManualSearchForm = {
  query: string;
  exact_phrase: boolean;
  title: string;
  issuer: string;
  document_number: string;
  document_type: string;
  family: string;
  version: string;
  status: "" | "current" | "superseded" | "draft";
  issued_from: string;
  issued_to: string;
  effective_from: string;
  effective_to: string;
  within_document: string;
};

const EMPTY_FORM: ManualSearchForm = {
  query: "",
  exact_phrase: false,
  title: "",
  issuer: "",
  document_number: "",
  document_type: "",
  family: "",
  version: "",
  status: "",
  issued_from: "",
  issued_to: "",
  effective_from: "",
  effective_to: "",
  within_document: "",
};

export function ManualDocumentSearch() {
  const search = useManualDocumentSearch();
  const [form, setForm] = useState<ManualSearchForm>(EMPTY_FORM);
  const [result, setResult] =
    useState<AskManualDocumentSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const requestRef = useRef<AskManualDocumentSearchRequest | null>(null);
  const sequenceRef = useRef(0);

  async function runSearch(
    request: AskManualDocumentSearchRequest,
    append: boolean,
  ) {
    const sequence = sequenceRef.current + 1;
    sequenceRef.current = sequence;
    setError(null);
    setValidation(null);
    try {
      const response = await search.mutateAsync(request);
      if (sequenceRef.current !== sequence) return;
      setResult((current) => {
        if (!append || current === null) return response;
        return {
          ...response,
          status: "complete",
          items: [...current.items, ...response.items],
        };
      });
    } catch (caught) {
      if (sequenceRef.current !== sequence) return;
      if (caught instanceof Error && caught.name === "ZodError") {
        setValidation(
          "Enter at least one valid search term or filter. Date ranges must run from earlier to later.",
        );
      } else {
        setError(
          "Manual document search is temporarily unavailable. Your filters are preserved.",
        );
      }
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const request = requestFrom(form);
    clearCanonicalRoute();
    requestRef.current = request;
    void runSearch(request, false);
  }

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const documentId = Number(params.get("document"));
    const registryVersionId = Number(params.get("version"));
    const validDocumentId =
      Number.isInteger(documentId) && documentId > 0;
    const validRegistryVersionId =
      Number.isInteger(registryVersionId) && registryVersionId > 0;
    if (
      !search.available ||
      (!validDocumentId && !validRegistryVersionId)
    ) {
      return;
    }
    const request: AskManualDocumentSearchRequest = {
      schema_version: "1",
      document_id: validDocumentId ? documentId : undefined,
      registry_version_id:
        validRegistryVersionId
          ? registryVersionId
          : undefined,
      exact_phrase: false,
      limit: 20,
    };
    requestRef.current = request;
    void runSearch(request, false);
    // The canonical URL identity is restored once per route mount.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function reset() {
    sequenceRef.current += 1;
    setForm(EMPTY_FORM);
    setResult(null);
    setError(null);
    setValidation(null);
    requestRef.current = null;
    clearCanonicalRoute();
  }

  return (
    <section className="manual-document-search" aria-labelledby="manual-search-title">
      <header>
        <div>
          <p>Official Regulatory Corpus</p>
          <h1 id="manual-search-title">Manual document search</h1>
          <span>
            Exact lexical search remains available when semantic or generated
            research is degraded.
          </span>
        </div>
        <FileSearch size={30} aria-hidden="true" />
      </header>

      <form onSubmit={submit} aria-label="Manual official document search">
        <div className="manual-search-primary">
          <label>
            Search terms
            <input
              value={form.query}
              onChange={(event) =>
                setForm({ ...form, query: event.target.value })
              }
              placeholder="Regulation title, number, or text"
            />
          </label>
          <label className="manual-search-check">
            <input
              type="checkbox"
              checked={form.exact_phrase}
              onChange={(event) =>
                setForm({
                  ...form,
                  exact_phrase: event.target.checked,
                })
              }
            />
            Match exact phrase
          </label>
        </div>

        <fieldset>
          <legend>Document metadata</legend>
          <FilterInput
            label="Title"
            value={form.title}
            onChange={(title) => setForm({ ...form, title })}
          />
          <FilterInput
            label="Issuer"
            value={form.issuer}
            onChange={(issuer) => setForm({ ...form, issuer })}
          />
          <FilterInput
            label="Document number"
            value={form.document_number}
            onChange={(document_number) =>
              setForm({ ...form, document_number })
            }
          />
          <FilterInput
            label="Document type"
            value={form.document_type}
            onChange={(document_type) =>
              setForm({ ...form, document_type })
            }
          />
          <FilterInput
            label="Family"
            value={form.family}
            onChange={(family) => setForm({ ...form, family })}
          />
          <FilterInput
            label="Version"
            value={form.version}
            onChange={(version) => setForm({ ...form, version })}
          />
          <label>
            Current status
            <select
              value={form.status}
              onChange={(event) =>
                setForm({
                  ...form,
                  status: event.target.value as ManualSearchForm["status"],
                })
              }
            >
              <option value="">All statuses</option>
              <option value="current">Current</option>
              <option value="superseded">Superseded</option>
              <option value="draft">Draft</option>
            </select>
          </label>
          <FilterInput
            label="Within-document text"
            value={form.within_document}
            onChange={(within_document) =>
              setForm({ ...form, within_document })
            }
          />
        </fieldset>

        <fieldset>
          <legend>Dates</legend>
          <DateInput
            label="Issued from"
            value={form.issued_from}
            onChange={(issued_from) => setForm({ ...form, issued_from })}
          />
          <DateInput
            label="Issued to"
            value={form.issued_to}
            onChange={(issued_to) => setForm({ ...form, issued_to })}
          />
          <DateInput
            label="Effective from"
            value={form.effective_from}
            onChange={(effective_from) =>
              setForm({ ...form, effective_from })
            }
          />
          <DateInput
            label="Effective to"
            value={form.effective_to}
            onChange={(effective_to) =>
              setForm({ ...form, effective_to })
            }
          />
        </fieldset>

        <div className="manual-search-actions">
          <button type="submit" disabled={!search.available || search.isPending}>
            <Search size={17} aria-hidden="true" />
            {search.isPending ? "Searching" : "Search official documents"}
          </button>
          <button type="button" onClick={reset}>
            <RotateCcw size={16} aria-hidden="true" />
            Clear
          </button>
        </div>
      </form>

      {!search.available ? (
        <p className="manual-search-error" role="alert">
          Manual document search is not enabled in this rollout.
        </p>
      ) : null}
      {validation !== null ? (
        <p className="manual-search-error" role="alert">{validation}</p>
      ) : null}
      {error !== null ? (
        <p className="manual-search-error" role="alert">{error}</p>
      ) : null}
      {search.isPending ? (
        <p className="manual-search-status" role="status">
          Searching stored official document metadata and text…
        </p>
      ) : null}
      {result?.status === "no_match" ? (
        <p className="manual-search-status" role="status">
          No official document matched these exact terms and filters.
        </p>
      ) : null}
      {result !== null && result.items.length > 0 ? (
        <ManualSearchResults
          result={result}
          onNext={() => {
            if (
              result.next_cursor === null ||
              requestRef.current === null
            ) {
              return;
            }
            void runSearch(
              {
                ...requestRef.current,
                cursor: result.next_cursor,
              },
              true,
            );
          }}
          loading={search.isPending}
        />
      ) : null}
    </section>
  );
}

function ManualSearchResults({
  result,
  onNext,
  loading,
}: {
  result: AskManualDocumentSearchResponse;
  onNext: () => void;
  loading: boolean;
}) {
  return (
    <section className="manual-search-results" aria-labelledby="manual-results-title">
      <header>
        <div>
          <p>Exact official results</p>
          <h2 id="manual-results-title">Documents</h2>
        </div>
        <span>Status evaluated as of {result.as_of}</span>
      </header>
      <ol>
        {result.items.map((item) => (
          <li key={item.result_id}>
            <ManualSearchResult item={item} />
          </li>
        ))}
      </ol>
      {result.next_cursor !== null ? (
        <button type="button" onClick={onNext} disabled={loading}>
          Load more exact results
        </button>
      ) : null}
    </section>
  );
}

function ManualSearchResult({
  item,
}: {
  item: AskManualDocumentSearchItem;
}) {
  return (
    <article className="manual-search-result">
      <header>
        <div>
          <p>{item.status.replaceAll("_", " ")}</p>
          <h3>{item.title}</h3>
        </div>
        <span>{item.metadata_state} metadata</span>
      </header>
      <p>{item.why_matched}</p>
      <dl>
        <Metadata label="Issuer" value={item.issuer} />
        <Metadata label="Document number" value={item.document_number} />
        <Metadata label="Type" value={item.document_type} />
        <Metadata label="Jurisdiction" value={item.jurisdiction} />
        <Metadata label="Issue date" value={item.issue_date} />
        <Metadata label="Effective date" value={item.effective_date} />
        <Metadata label="Family" value={item.family_title} />
        <Metadata label="Version" value={item.version_label} />
      </dl>
      {item.within_document_matches.map((match) => (
        <blockquote key={match.chunk_id}>
          <p>{match.excerpt}</p>
          <cite>
            {match.section_title ?? "Section not established"}
            {" · "}
            {match.page_number === null
              ? "Page not established"
              : `Page ${match.page_number}`}
          </cite>
        </blockquote>
      ))}
      <a
        href={item.source_url}
        target="_blank"
        rel="noreferrer"
      >
        Open official source
        <ExternalLink size={15} aria-hidden="true" />
      </a>
    </article>
  );
}

function FilterInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <input
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function DateInput({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <label>
      {label}
      <input
        type="date"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}

function Metadata({
  label,
  value,
}: {
  label: string;
  value: string | null;
}) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value ?? "Not established"}</dd>
    </div>
  );
}

function requestFrom(
  form: ManualSearchForm,
): AskManualDocumentSearchRequest {
  const optional = (value: string) => value || undefined;
  return {
    schema_version: "1",
    query: optional(form.query),
    exact_phrase: form.exact_phrase,
    title: optional(form.title),
    issuer: optional(form.issuer),
    document_number: optional(form.document_number),
    document_type: optional(form.document_type),
    family: optional(form.family),
    version: optional(form.version),
    status: form.status || undefined,
    issued_from: optional(form.issued_from),
    issued_to: optional(form.issued_to),
    effective_from: optional(form.effective_from),
    effective_to: optional(form.effective_to),
    within_document: optional(form.within_document),
    limit: 20,
  };
}

function clearCanonicalRoute() {
  const url = new URL(window.location.href);
  if (
    !url.searchParams.has("document") &&
    !url.searchParams.has("version")
  ) {
    return;
  }
  url.searchParams.delete("document");
  url.searchParams.delete("version");
  window.history.pushState(
    {},
    "",
    `${url.pathname}${url.search}${url.hash}`,
  );
}
