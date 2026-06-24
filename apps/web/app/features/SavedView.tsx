import { CalendarClock, MessageSquareText, Star } from "lucide-react";

import { EventCard } from "@/app/components/events/EventCard";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { MetricCard } from "@/app/components/ui/MetricCard";
import { isConsultation } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function SavedView() {
  const { savedEvents, activeDeadlines, busyAction, handleBookmark, digestStatus } = useWorkspace();

  if (digestStatus.isLoading) {
    return <LoadingState label="Loading saved intelligence..." />;
  }
  if (digestStatus.isError) {
    return (
      <ErrorState
        title="Unable to load saved items"
        error={digestStatus.error}
        onRetry={digestStatus.refetch}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="metric-grid three">
        <MetricCard title="Saved Events" value={savedEvents.length} Icon={Star} tone="purple" />
        <MetricCard title="Saved Deadlines" value={activeDeadlines.length} Icon={CalendarClock} tone="green" />
        <MetricCard
          title="Saved Consultations"
          value={savedEvents.filter(isConsultation).length}
          Icon={MessageSquareText}
          tone="amber"
        />
      </section>
      <section className="event-list">
        {savedEvents.map((event) => (
          <EventCard
            key={event.id}
            event={event}
            onBookmark={() => void handleBookmark(event)}
            busy={busyAction === `bookmark-${event.id}`}
          />
        ))}
        {!savedEvents.length ? (
          <EmptyState title="No saved intelligence" body="Use the bookmark action on any update to save it here." />
        ) : null}
      </section>
    </div>
  );
}
