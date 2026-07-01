import { KeyRound, LogOut, ShieldCheck, UserCircle } from "lucide-react";

import { Panel } from "@/app/components/ui/Panel";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function AccountView() {
  const { userEmail, isAuthenticated, isAdmin, handleSignOut } = useWorkspace();
  return (
    <section className="two-column ops-page">
      <Panel title="Profile" icon={UserCircle}>
        <div className="profile-card">
          <img src="/logo_mark.png" alt="Resolven logo" />
          <div>
            <h3>{userEmail || "Public reader"}</h3>
            <p>{isAuthenticated ? "Authenticated user" : "Browsing without a session"}</p>
          </div>
        </div>
        {isAuthenticated ? (
          <div className="account-actions">
            <button type="button" className="danger-button" onClick={() => void handleSignOut()}>
              <LogOut size={16} />
              Sign out
            </button>
          </div>
        ) : null}
      </Panel>

      <Panel title="Access & Security" icon={ShieldCheck}>
        <div className="ops-summary-grid">
          <div className="detail-fact">
            <span>Role</span>
            <strong>{isAdmin ? "Admin" : isAuthenticated ? "User" : "Public reader"}</strong>
          </div>
          <div className="detail-fact">
            <span>Session</span>
            <strong>{isAuthenticated ? "Supabase session" : "Anonymous"}</strong>
          </div>
          <div className="detail-fact">
            <span>Subscription</span>
            <strong>Workspace access active</strong>
          </div>
          <div className="detail-fact">
            <span>MFA</span>
            <strong>Not exposed by current API</strong>
          </div>
        </div>
      </Panel>

      <Panel title="API Keys" icon={KeyRound}>
        <p className="lead-copy">
          API key management is not exposed by the current frontend API surface. This panel is intentionally read-only
          until a backend key endpoint exists.
        </p>
      </Panel>
    </section>
  );
}
