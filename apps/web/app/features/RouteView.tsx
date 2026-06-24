import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { AccountView } from "./AccountView";
import {
  AdminAnalyticsView,
  AdminCheckpointsView,
  AdminDashboardView,
  AdminDocumentsView,
  AdminEventsView,
  AdminFamiliesView,
  AdminGate,
  AdminPagesView,
  AdminRunsView,
  AdminSourcesView,
} from "./AdminViews";
import { AskView } from "./AskView";
import { DashboardView } from "./DashboardView";
import { DeadlinesView } from "./DeadlinesView";
import { EventDetailView } from "./EventDetailView";
import { IntelligenceView } from "./IntelligenceView";
import { LatestView } from "./LatestView";
import { NotificationsView } from "./NotificationsView";
import { SavedView } from "./SavedView";
import { DocsView, FlowView } from "./StaticViews";

export function RouteView() {
  const { route } = useWorkspace();
  switch (route) {
    case "dashboard":
      return <DashboardView />;
    case "latest":
      return <LatestView />;
    case "intelligence":
      return <IntelligenceView />;
    case "deadlines":
      return <DeadlinesView />;
    case "ask":
      return <AskView />;
    case "saved":
      return <SavedView />;
    case "event":
      return <EventDetailView />;
    case "notifications":
      return <NotificationsView />;
    case "account":
      return <AccountView />;
    case "admin-dashboard":
      return (
        <AdminGate>
          <AdminDashboardView />
        </AdminGate>
      );
    case "admin-sources":
      return (
        <AdminGate>
          <AdminSourcesView />
        </AdminGate>
      );
    case "admin-pages":
      return (
        <AdminGate>
          <AdminPagesView />
        </AdminGate>
      );
    case "admin-runs":
      return (
        <AdminGate>
          <AdminRunsView />
        </AdminGate>
      );
    case "admin-events":
      return (
        <AdminGate>
          <AdminEventsView />
        </AdminGate>
      );
    case "admin-documents":
      return (
        <AdminGate>
          <AdminDocumentsView />
        </AdminGate>
      );
    case "admin-families":
      return (
        <AdminGate>
          <AdminFamiliesView />
        </AdminGate>
      );
    case "admin-checkpoints":
      return (
        <AdminGate>
          <AdminCheckpointsView />
        </AdminGate>
      );
    case "admin-analytics":
      return (
        <AdminGate>
          <AdminAnalyticsView />
        </AdminGate>
      );
    case "api-docs":
      return <DocsView />;
    case "flow":
      return <FlowView />;
    default:
      return <DashboardView />;
  }
}
