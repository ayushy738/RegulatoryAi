import { BookOpenText, Network } from "lucide-react";

import { Panel } from "@/app/components/ui/Panel";

export function DocsView() {
  return (
    <Panel title="API Documentation" icon={BookOpenText}>
      <p className="lead-copy">
        The app uses existing Resolven backend APIs for auth, events, intelligence, chat, admin sources, source
        pages, crawl runs, checkpoints, documents, families, exports, and analytics.
      </p>
      <div className="doc-grid">
        {[
          ["Auth", "/auth/profile, Supabase session"],
          ["Events", "/events, /events/{id}, /exports/latest"],
          ["Intelligence", "/intelligence/deadlines, /obligations, /stakeholders, /readiness"],
          ["Chat", "/chat, /chat/history"],
          [
            "Admin",
            "/admin/sources, /admin/pages, /admin/checkpoints, /admin/documents, /admin/events, /admin/families, /admin/analytics",
          ],
        ].map(([title, text]) => (
          <div key={title}>
            <strong>{title}</strong>
            <p>{text}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

export function FlowView() {
  return (
    <Panel title="Data Flow" icon={Network}>
      <div className="flow-steps">
        {[
          "Curated source page",
          "Source-specific parser",
          "Primary document acquisition",
          "Extraction and OCR",
          "Family and version registry",
          "Knowledge graph",
          "Intelligence gate",
          "User-facing event",
        ].map((step, index) => (
          <div key={step}>
            <span>{index + 1}</span>
            <strong>{step}</strong>
          </div>
        ))}
      </div>
    </Panel>
  );
}
