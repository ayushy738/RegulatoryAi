import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import { AdminDashboardView, AdminGate } from "./AdminViews";
import { AdminRunDetailView } from "./admin/AdminRunDetailView";
import { AdminRunsView } from "./admin/AdminRunsView";
import { AdminSourcesView } from "./admin/AdminSourcesView";
import { AdminUsersView } from "./admin/AdminUsersView";
import { AskRoute } from "./AskRoute";
import { DashboardView } from "./DashboardView";
import { DeadlinesView } from "./DeadlinesView";
import { EventDetailView } from "./EventDetailView";
import { IntelligenceView } from "./IntelligenceView";
import { LatestView } from "./LatestView";
import { ManualDocumentSearchRoute } from "./ManualDocumentSearchRoute";
import { NotificationsView } from "./NotificationsView";
import { SavedView } from "./SavedView";
import { DocsView, FlowView } from "./StaticViews";

export function RouteView() {
  const { route, v2AskEnabled, initialRunId } = useWorkspace();
  switch (route) {
    case "dashboard":
      return <DashboardView />;
    case "latest":
      return <LatestView />;
    case "browse":
      return v2AskEnabled ? <ManualDocumentSearchRoute /> : <LatestView />;
    case "intelligence":
      return <IntelligenceView />;
    case "deadlines":
      return <DeadlinesView />;
    case "ask":
      return <AskRoute />;
    case "saved":
      return <SavedView />;
    case "event":
      return <EventDetailView />;
    case "notifications":
    case "notification-preferences":
      return <NotificationsView />;
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
    case "admin-runs":
      return (
        <AdminGate>
          <AdminRunsView />
        </AdminGate>
      );
    case "admin-run":
      return (
        <AdminGate>
          <AdminRunDetailView runId={initialRunId ?? 0} />
        </AdminGate>
      );
    case "admin-users":
      return (
        <AdminGate>
          <AdminUsersView />
        </AdminGate>
      );
    case "api-docs":
      return <DocsView />;
    case "flow":
      return <FlowView />;
    default:
      return <LatestView />;
  }
}
