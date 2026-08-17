"use client";

import { ExternalLink } from "lucide-react";

import { Button } from "@/app/components/ui/Button";
import { Fact, FactList, SectionHeader } from "@/app/components/ui/PageHeader";
import { Overlay } from "@/app/components/ui/Overlay";
import { cleanText, formatShortDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

/**
 * Provenance for whatever the analyst just clicked. A drawer rather than a page
 * so the reader keeps their place in the feed; on mobile it becomes a
 * full-screen sheet through the shared overlay.
 */
export function EvidenceDrawer() {
  const { selectedEvidence, setSelectedEvidence } = useWorkspace();
  if (!selectedEvidence) return null;

  const relationships = selectedEvidence.relationships ?? [];
  const close = () => setSelectedEvidence(null);

  return (
    <Overlay
      open
      variant="drawer"
      title={cleanText(selectedEvidence.title)}
      description="Source evidence"
      onClose={close}
      footer={
        <>
          {selectedEvidence.sourceUrl ? (
            <a
              className="rv-btn rv-btn--primary"
              href={selectedEvidence.sourceUrl}
              target="_blank"
              rel="noreferrer"
            >
              <ExternalLink size={16} aria-hidden />
              <span>Open source</span>
            </a>
          ) : null}
          <Button variant="secondary" onClick={close}>
            Done
          </Button>
        </>
      }
    >
      <div className="rv-stack">
        <FactList ariaLabel="Evidence provenance">
          <Fact label="Issuer" value={selectedEvidence.issuer ?? "Unknown"} />
          <Fact
            label="Date"
            value={formatShortDate(selectedEvidence.date) ?? "Not stated"}
          />
          <Fact
            label="Document"
            value={
              selectedEvidence.documentId ? `#${selectedEvidence.documentId}` : "Not linked"
            }
          />
          <Fact
            label="Chunk"
            value={
              selectedEvidence.chunkId
                ? `#${selectedEvidence.chunkId}`
                : "Graph or summary evidence"
            }
          />
          <Fact label="Family" value={selectedEvidence.family ?? "Not assigned"} />
          <Fact label="Version" value={selectedEvidence.version ?? "Latest available"} />
        </FactList>

        {selectedEvidence.summary ? (
          <section className="rv-section">
            <SectionHeader as="h3" title="Analyst summary" />
            <p className="rv-prose">{cleanText(selectedEvidence.summary)}</p>
          </section>
        ) : null}

        <section className="rv-section">
          <SectionHeader as="h3" title="Extracted evidence" />
          <p className="rv-prose">
            {cleanText(
              selectedEvidence.evidence,
              "No extracted evidence text was returned for this item.",
            )}
          </p>
        </section>

        <section className="rv-section">
          <SectionHeader as="h3" title="Graph relations" />
          {relationships.length ? (
            <ul className="rv-notes">
              {relationships.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          ) : (
            <p className="rv-helper">No relationship rows were returned for this item.</p>
          )}
        </section>
      </div>
    </Overlay>
  );
}
