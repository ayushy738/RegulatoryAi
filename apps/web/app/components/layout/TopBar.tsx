import type { NormalizedRoute, PipelineStatus } from "@/app/workspace/types";

function MaterialIcon({ children }: { children: string }) {
  return <span className="material-symbols-outlined">{children}</span>;
}

export function TopBar({
  route,
  digestDate,
  pipelineStatus,
  eventCount,
  isAdmin,
}: {
  route: NormalizedRoute;
  digestDate: string;
  pipelineStatus: PipelineStatus;
  eventCount: number;
  isAdmin: boolean;
}) {
  return (
    <header className="topbar">
      <div className="stitch-search-shell">
        <MaterialIcon>search</MaterialIcon>
        <input placeholder="Search regulations, stakeholders..." type="text" />
      </div>
      <div className="topbar-actions">
        <button className="stitch-icon-button has-alert" type="button" aria-label="Notifications">
          <MaterialIcon>notifications</MaterialIcon>
        </button>
        <button className="stitch-icon-button" type="button" aria-label="Settings">
          <MaterialIcon>settings</MaterialIcon>
        </button>
        <a className="stitch-avatar" href="/account" aria-label="Account">
          {(route === "landing" ? "R" : "A").toUpperCase()}
        </a>
      </div>
    </header>
  );
}
