import { useWorkspace } from "@/app/workspace/WorkspaceContext";

import {
  AdminDashboardView,
  AdminGate,
  AdminRunsView,
  AdminSourcesView,
  AdminUsersView,
} from "./AdminViews";
import { AskRoute } from "./AskRoute";
import { DashboardView } from "./DashboardView";
import { DeadlinesView } from "./DeadlinesView";
import { EventDetailView } from "./EventDetailView";
import { IntelligenceView } from "./IntelligenceView";
import { LatestView } from "./LatestView";
import { ManualDocumentSearchRoute } from "./ManualDocumentSearchRoute";
import { SavedView } from "./SavedView";
import { DocsView, FlowView } from "./StaticViews";

export function RouteView() {
  const { route, v2AskEnabled } = useWorkspace();
  switch (route) {
    case "dashboard":
      return <DashboardView />;
    case "latest":
      return <LatestView />;
    case "browse":
      return v2AskEnabled
        ? <ManualDocumentSearchRoute />
        : <LatestView />;
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
      return <AdminGate><AdminSourcesView /></AdminGate>;
    case "admin-runs":
      return (
        <AdminGate>
          <AdminRunsView />
        </AdminGate>
      );
    case "admin-events":
    case "admin-documents":
    case "admin-families":
    case "admin-versions":
    case "admin-graph":
    case "admin-rag":
    case "admin-queues":
    case "admin-checkpoints":
    case "admin-analytics":
    case "admin-subscriptions":
      return <AdminGate><AdminRunsView /></AdminGate>;
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
      return <DashboardView />;
  }
}
