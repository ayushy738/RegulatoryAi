import { ExternalLink, FileText, X } from "lucide-react";

import { cleanText, formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function EvidenceDrawer() {
  const { selectedEvidence, setSelectedEvidence } = useWorkspace();
  if (!selectedEvidence) return null;
  const relationships = selectedEvidence.relationships ?? [];
  return (
    <aside className="evidence-drawer" aria-label="Source evidence">
      <header>
        <div>
          <span>Source Evidence</span>
          <h2>{cleanText(selectedEvidence.title)}</h2>
        </div>
        <button type="button" aria-label="Close evidence drawer" onClick={() => setSelectedEvidence(null)}>
          <X size={18} />
        </button>
      </header>

      <dl className="evidence-meta">
        <div>
          <dt>Issuer</dt>
          <dd>{selectedEvidence.issuer ?? "Unknown"}</dd>
        </div>
        <div>
          <dt>Date</dt>
          <dd>{formatDate(selectedEvidence.date)}</dd>
        </div>
        <div>
          <dt>Document</dt>
          <dd>{selectedEvidence.documentId ? `#${selectedEvidence.documentId}` : "Not linked"}</dd>
        </div>
        <div>
          <dt>Chunk</dt>
          <dd>{selectedEvidence.chunkId ? `#${selectedEvidence.chunkId}` : "Graph or summary evidence"}</dd>
        </div>
        <div>
          <dt>Family</dt>
          <dd>{selectedEvidence.family ?? "Not assigned"}</dd>
        </div>
        <div>
          <dt>Version</dt>
          <dd>{selectedEvidence.version ?? "Latest available"}</dd>
        </div>
      </dl>

      {selectedEvidence.summary ? (
        <section>
          <h3>Analyst Summary</h3>
          <p>{cleanText(selectedEvidence.summary)}</p>
        </section>
      ) : null}

      <section>
        <h3>Extracted Evidence</h3>
        <p>{cleanText(selectedEvidence.evidence, "No extracted evidence text was returned by this API.")}</p>
      </section>

      <section>
        <h3>Graph Relations</h3>
        {relationships.length ? (
          <ul>
            {relationships.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : (
          <p>No relationship rows were returned for this item.</p>
        )}
      </section>

      <footer>
        {selectedEvidence.sourceUrl ? (
          <a href={selectedEvidence.sourceUrl} target="_blank" rel="noreferrer">
            <ExternalLink size={16} />
            Open source
          </a>
        ) : null}
        <button type="button" onClick={() => setSelectedEvidence(null)}>
          <FileText size={16} />
          Done
        </button>
      </footer>
    </aside>
  );
}
