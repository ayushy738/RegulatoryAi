import { useMemo, useState } from "react";
import { Download, ExternalLink, FileText, GitCompareArrows, Network, Search } from "lucide-react";

import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { Panel } from "@/app/components/ui/Panel";
import { clampText, cleanText, formatDate, formatRelativeDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function DocumentsView() {
  const { adminDocs, families, adminStatus, query, setQuery, setSelectedEvidence } = useWorkspace();
  const [familyFilter, setFamilyFilter] = useState("all");
  const [typeFilter, setTypeFilter] = useState("all");
  const documentTypes = useMemo(
    () => Array.from(new Set(adminDocs.map((doc) => doc.doc_type ?? "unknown"))).sort(),
    [adminDocs],
  );
  const filteredDocs = useMemo(() => {
    const q = query.toLowerCase().trim();
    return adminDocs.filter((doc) => {
      if (q) {
        const text = cleanText(
          `${doc.title} ${doc.issuing_body ?? ""} ${doc.source_code ?? ""} ${doc.family_title ?? ""}`,
          "",
        ).toLowerCase();
        if (!text.includes(q)) return false;
      }
      if (familyFilter !== "all" && String(doc.family_id ?? "") !== familyFilter) return false;
      if (typeFilter !== "all" && (doc.doc_type ?? "unknown") !== typeFilter) return false;
      return true;
    });
  }, [adminDocs, familyFilter, query, typeFilter]);

  if (adminStatus.isLoading) return <LoadingState label="Loading documents..." />;
  if (adminStatus.isError) {
    return <ErrorState title="Unable to load documents" error={adminStatus.error} onRetry={adminStatus.refetch} />;
  }

  return (
    <div className="page-stack ops-page">
      <section className="ops-page-header">
        <div>
          <span>Document Registry</span>
          <h1>Primary documents, families, and versions</h1>
          <p>Search accepted documents, inspect source evidence, compare family membership, and open originals.</p>
        </div>
        <div className="ops-stat-strip">
          <strong>{adminDocs.length}</strong>
          <span>documents</span>
          <strong>{families.length}</strong>
          <span>families</span>
        </div>
      </section>

      <section className="toolbar-panel document-toolbar" aria-label="Document filters">
        <label className="search-box">
          <Search size={17} />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search documents" />
        </label>
        <label className="select-field">
          <span>Family</span>
          <select value={familyFilter} onChange={(event) => setFamilyFilter(event.target.value)}>
            <option value="all">All families</option>
            {families.map((family) => (
              <option key={family.family_id} value={family.family_id}>
                {family.canonical_title}
              </option>
            ))}
          </select>
        </label>
        <label className="select-field">
          <span>Type</span>
          <select value={typeFilter} onChange={(event) => setTypeFilter(event.target.value)}>
            <option value="all">All types</option>
            {documentTypes.map((type) => (
              <option key={type} value={type}>
                {type}
              </option>
            ))}
          </select>
        </label>
      </section>

      <div className="document-layout">
        <Panel title="Document Explorer" icon={FileText}>
          <div className="document-list">
            {filteredDocs.map((doc) => (
              <article className="document-row" key={doc.id}>
                <div>
                  <div className="row-wrap">
                    <span className="mini-badge">{doc.source_code ?? "SRC"}</span>
                    <span className="tag">{doc.doc_type ?? "unknown"}</span>
                    <span className="tag green">{doc.family_title ? "Family linked" : "Unassigned"}</span>
                  </div>
                  <h3>{cleanText(doc.title)}</h3>
                  <p>
                    {doc.issuing_body ?? "Unknown issuer"} | {formatDate(doc.issue_date)} | Seen{" "}
                    {formatRelativeDate(doc.last_seen_at)}
                  </p>
                  <p>{clampText(doc.family_title ?? doc.source_url, 180)}</p>
                </div>
                <div className="document-actions">
                  <button
                    type="button"
                    onClick={() =>
                      setSelectedEvidence({
                        title: doc.title,
                        issuer: doc.issuing_body,
                        date: doc.issue_date,
                        summary: doc.family_title,
                        evidence: doc.source_url,
                        sourceUrl: doc.source_url,
                        family: doc.family_title,
                        version: doc.latest_version_id,
                        documentId: doc.id,
                        relationships: [
                          doc.source_code ? `Source: ${doc.source_code}` : "Source not classified",
                          doc.family_title ? `Family: ${doc.family_title}` : "No family assignment",
                        ],
                      })
                    }
                  >
                    <Network size={16} />
                    Evidence
                  </button>
                  <a href={doc.source_url} target="_blank" rel="noreferrer">
                    <ExternalLink size={16} />
                    Source
                  </a>
                  <a href={doc.source_url} target="_blank" rel="noreferrer" download>
                    <Download size={16} />
                    Download
                  </a>
                </div>
              </article>
            ))}
            {!filteredDocs.length ? (
              <EmptyState title="No documents match" body="Adjust search or filters to inspect accepted documents." />
            ) : null}
          </div>
        </Panel>

        <Panel title="Families & Versions" icon={GitCompareArrows}>
          <div className="family-list">
            {families.slice(0, 12).map((family) => (
              <button
                type="button"
                key={family.family_id}
                className={familyFilter === family.family_id ? "active" : ""}
                onClick={() => setFamilyFilter(String(family.family_id))}
              >
                <strong>{cleanText(family.canonical_title)}</strong>
                <span>
                  {family.document_count} docs | {family.version_count} versions | {family.deadline_count} deadlines
                </span>
              </button>
            ))}
            {!families.length ? (
              <EmptyState title="No families" body="Family registry data was not returned by the admin API." />
            ) : null}
          </div>
        </Panel>
      </div>
    </div>
  );
}
