import { ShieldCheck, UserCircle } from "lucide-react";

import { Panel } from "@/app/components/ui/Panel";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function AccountView() {
  const { userEmail, demoMode, isAdmin } = useWorkspace();
  return (
    <section className="two-column">
      <Panel title="Profile" icon={UserCircle}>
        <div className="profile-card">
          <img src="/logo_mark.png" alt="Resolven logo" />
          <div>
            <h3>{userEmail}</h3>
            <p>{demoMode ? "Local preview user" : "Authenticated user"}</p>
          </div>
        </div>
      </Panel>
      <Panel title="Subscription" icon={ShieldCheck}>
        <p className="lead-copy">Resolven Regulatory AI workspace access is active.</p>
        <p>Role: {isAdmin || demoMode ? "Admin" : "User"}</p>
      </Panel>
    </section>
  );
}
