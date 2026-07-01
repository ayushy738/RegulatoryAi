import Link from "next/link";
import { CalendarClock, FileText, MessageSquareText, Star } from "lucide-react";

import { EventCard } from "@/app/components/events/EventCard";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { MetricCard } from "@/app/components/ui/MetricCard";
import { clampText, formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function SavedView() {
  const {
    savedEvents,
    activeDeadlines,
    adminDocs,
    chatMessages,
    busyAction,
    handleBookmark,
    digestStatus,
    setSelectedEvidence,
  } = useWorkspace();
  const savedUrls = new Set(savedEvents.map((event) => event.source_url));
  const savedDocs = adminDocs.filter((doc) => savedUrls.has(doc.source_url));
  const savedDeadlines = activeDeadlines.filter((deadline) => savedUrls.has(deadline.source_url));
  const savedConversations = chatMessages.filter((message) => message.role === "user").slice(-8);

  if (digestStatus.isLoading) return <LoadingState label="Loading saved intelligence..." />;
  if (digestStatus.isError) {
    return <ErrorState title="Unable to load saved items" error={digestStatus.error} onRetry={digestStatus.refetch} />;
  }

  return (
    <div className="page-stack ops-page saved-workspace">
      <section className="ops-page-header premium-page-header">
        <div>
          <span>Saved Workbench</span>
          <h1>Saved intelligence</h1>
          <p>Bookmarked events plus their related documents, deadlines, and available conversation history.</p>
        </div>
      </section>
      <section className="metric-grid four">
        <MetricCard title="Saved Events" value={savedEvents.length} Icon={Star} tone="purple" />
        <MetricCard title="Related Documents" value={savedDocs.length} Icon={FileText} tone="green" />
        <MetricCard title="Related Deadlines" value={savedDeadlines.length} Icon={CalendarClock} tone="amber" />
        <MetricCard title="Conversations" value={savedConversations.length} Icon={MessageSquareText} tone="red" />
      </section>

      <section className="saved-grid">
        <div className="ops-panel">
          <header>
            <h2>Events</h2>
            <Link href="/latest">Browse feed</Link>
          </header>
          <div className="event-list">
            {savedEvents.map((event) => (
              <EventCard
                key={event.id}
                event={event}
                onBookmark={() => void handleBookmark(event)}
                busy={busyAction === `bookmark-${event.id}`}
              />
            ))}
            {!savedEvents.length ? (
              <EmptyState title="No saved events" body="Use the bookmark action on any update to save it here." />
            ) : null}
          </div>
        </div>

        <div className="ops-panel">
          <header>
            <h2>Documents</h2>
            <span>From saved events</span>
          </header>
          <div className="ops-mini-list">
            {savedDocs.map((doc) => (
              <button
                type="button"
                key={doc.id}
                onClick={() =>
                  setSelectedEvidence({
                    title: doc.title,
                    issuer: doc.issuing_body,
                    date: doc.issue_date,
                    sourceUrl: doc.source_url,
                    family: doc.family_title,
                    version: doc.latest_version_id,
                    documentId: doc.id,
                    evidence: doc.source_url,
                  })
                }
              >
                <strong>{doc.title}</strong>
                <span>{doc.source_code ?? "unknown"} | {formatDate(doc.issue_date)}</span>
              </button>
            ))}
            {!savedDocs.length ? <EmptyState title="No related documents" body="No document rows matched saved event sources." /> : null}
          </div>
        </div>

        <div className="ops-panel">
          <header>
            <h2>Deadlines</h2>
            <Link href="/intelligence">Open intelligence</Link>
          </header>
          <div className="ops-mini-list">
            {savedDeadlines.map((deadline) => (
              <button
                type="button"
                key={`${deadline.document_id}-${deadline.deadline_type}`}
                onClick={() =>
                  setSelectedEvidence({
                    title: deadline.title,
                    issuer: deadline.issuer,
                    date: deadline.deadline_date,
                    sourceUrl: deadline.source_url,
                    evidence: deadline.evidence,
                    documentId: deadline.document_id,
                    relationships: deadline.stakeholders_affected.map((item) => `Affects ${item}`),
                  })
                }
              >
                <strong>{deadline.title}</strong>
                <span>{deadline.days_remaining ?? "--"} days | {formatDate(deadline.deadline_date)}</span>
              </button>
            ))}
            {!savedDeadlines.length ? <EmptyState title="No related deadlines" body="No active deadlines match saved event sources." /> : null}
          </div>
        </div>

        <div className="ops-panel">
          <header>
            <h2>Conversations</h2>
            <Link href="/ask">Ask AI</Link>
          </header>
          <div className="ops-mini-list">
            {savedConversations.map((message, index) => (
              <button type="button" key={`${message.content}-${index}`}>
                <strong>Question</strong>
                <span>{clampText(message.content, 140)}</span>
              </button>
            ))}
            {!savedConversations.length ? (
              <EmptyState title="No conversations loaded" body="Ask AI history is available after the chat history endpoint returns messages." />
            ) : null}
          </div>
        </div>
      </section>
    </div>
  );
}
