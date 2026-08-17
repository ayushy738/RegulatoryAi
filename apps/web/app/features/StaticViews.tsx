import { PageHeader, SectionHeader } from "@/app/components/ui/PageHeader";

const API_GROUPS: Array<[string, string]> = [
  ["Auth", "/auth/profile, Supabase session"],
  ["Events", "/events, /events/{id}, /exports/latest"],
  ["Intelligence", "/intelligence/deadlines, /stakeholders, /readiness"],
  ["Chat", "/chat, /chat/history"],
  ["Admin", "/admin, /admin/sources, /admin/runs, /admin/users"],
];

const PIPELINE_STEPS = [
  "Curated source page",
  "Source-specific parser",
  "Primary document acquisition",
  "Extraction and OCR",
  "Family and version registry",
  "Knowledge graph",
  "Intelligence gate",
  "User-facing event",
];

export function DocsView() {
  return (
    <div className="rv-page rv-page--reading">
      <PageHeader
        eyebrow="Reference"
        title="API documentation"
        description="Resolven surfaces are built on the existing backend APIs for auth, events, intelligence, chat and admin operations."
      />
      <section className="rv-section">
        <SectionHeader title="Endpoint groups" />
        <div className="rv-card">
          <dl className="rv-facts">
            {API_GROUPS.map(([title, text]) => (
              <div className="rv-fact" key={title}>
                <dt className="rv-fact__label">{title}</dt>
                <dd className="rv-fact__value">{text}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>
    </div>
  );
}

export function FlowView() {
  return (
    <div className="rv-page rv-page--reading">
      <PageHeader
        eyebrow="Reference"
        title="Data flow"
        description="How a published regulatory document becomes a user-facing intelligence event."
      />
      <ol className="rv-timeline">
        {PIPELINE_STEPS.map((step, index) => (
          <li className="rv-timeline__item" key={step}>
            <span className="rv-timeline__marker" aria-hidden />
            <div className="rv-timeline__body">
              <span className="rv-cell-primary">
                {index + 1}. {step}
              </span>
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}
