function MaterialIcon({ children, filled = false }: { children: string; filled?: boolean }) {
  return (
    <span className="material-symbols-outlined" style={filled ? { fontVariationSettings: "'FILL' 1" } : undefined}>
      {children}
    </span>
  );
}

export function LandingPage({
  canRead,
  email,
  password,
  authMessage,
  onEmail,
  onPassword,
  onSignIn,
  onMagicLink,
  onDemo,
}: {
  canRead: boolean;
  email: string;
  password: string;
  authMessage: string;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onSignIn: () => void;
  onMagicLink: () => void;
  onDemo: () => void;
}) {
  return (
    <main className="stitch-landing">
      <nav className="stitch-landing-nav">
        <a href="/" className="stitch-landing-brand">Resolven</a>
        <div>
          <a href="/dashboard">Sign In</a>
          <a className="stitch-landing-button" href="mailto:hello@resolven.ai">Book Demo</a>
        </div>
      </nav>

      <section className="stitch-landing-hero">
        <div className="stitch-landing-copy">
          <span className="stitch-landing-eyebrow">
            <MaterialIcon filled>auto_awesome</MaterialIcon>
            AI-POWERED INTELLIGENCE
          </span>
          <h1>Monitor Regulatory Changes Before They Impact Your Business</h1>
          <p>
            Precision-engineered monitoring for financial compliance, legal teams, and risk
            managers. Get ahead of deadlines with Stripe-quality automation.
          </p>
          <div className="stitch-landing-actions">
            <a className="stitch-landing-button primary" href={canRead ? "/dashboard" : "#signin"}>
              Start Monitoring
            </a>
            <a className="stitch-landing-button secondary" href="mailto:hello@resolven.ai">
              Book Demo <MaterialIcon>chevron_right</MaterialIcon>
            </a>
          </div>
          <div className="stitch-trust-strip">
            <span>Trusted by high-growth institutions</span>
            {["FINTECH-ONE", "LEGAL-FLOW", "RISK-NODE", "STABLE-CAP", "PRIME-LAW"].map((item) => (
              <strong key={item}>{item}</strong>
            ))}
          </div>
        </div>

        <div className="stitch-landing-status" id="signin">
          <div className="stitch-status-badge">
            <MaterialIcon>check_circle</MaterialIcon>
            <span>Status</span>
            <strong>Compliance Ready</strong>
          </div>
          <h2>Sign in</h2>
          <input value={email} onChange={(event) => onEmail(event.target.value)} placeholder="Email" />
          <input
            value={password}
            onChange={(event) => onPassword(event.target.value)}
            placeholder="Password"
            type="password"
          />
          <button className="stitch-landing-button primary full" type="button" onClick={onSignIn}>
            Sign In
          </button>
          <button className="stitch-landing-button secondary full" type="button" onClick={onMagicLink}>
            Send Magic Link
          </button>
          <button className="stitch-landing-button ghost full" type="button" onClick={onDemo}>
            Continue Local Preview
          </button>
          {authMessage ? <p className="notice">{authMessage}</p> : null}
        </div>
      </section>

      <section className="stitch-feature-section">
        <div className="stitch-section-intro">
          <h2>Intelligence at the Speed of Change</h2>
          <p>
            Our platform combines semantic AI with real-time regulatory feeds to give you a
            definitive edge in compliance monitoring.
          </p>
        </div>
        <div className="stitch-feature-grid">
          <FeatureCard icon="analytics" title="AI Monitoring" body="Real-time sentiment analysis and classification of regulatory updates from 400+ global sources including SEC, FCA, and ESMA." meta="420 Sources Live" extra="99.9% Accuracy" />
          <FeatureCard icon="event" title="Deadline Tracking" body="Never miss a filing date again. Automated calendar syncing and critical alert escalation for high-priority deadlines." />
          <FeatureCard icon="chat_bubble_outline" title="Ask AI" body="Query your internal regulatory library and public documents using natural language to get instant, cited answers." />
          <FeatureCard icon="groups" title="Stakeholder Impact" body="Automatically route relevant regulatory changes to specific departments and track acknowledgment across the organization." />
          <FeatureCard icon="quick_reference_all" title="Daily Digest" body="Every morning, receive a perfectly formatted briefing of only the most impactful changes tailored to your profile." />
          <FeatureCard icon="search_check" title="Consultation Tracking" body="Monitor active consultation papers from regulatory bodies and streamline your response contribution process." />
        </div>
      </section>

      <section className="stitch-tier-section">
        <div className="stitch-section-intro">
          <h2>Simple, Scalable Tiers</h2>
          <p>Designed for independent consultants up to global legal teams.</p>
        </div>
        <div className="stitch-tier-grid">
          <TierCard eyebrow="Individual" title="Guest" price="$0" cta="Get Started" items={["Public news feed access", "Up to 3 saved searches", "Basic email alerts"]} />
          <TierCard eyebrow="Most Popular" title="User" price="$199" cta="Upgrade Now" featured items={["Full AI Monitoring Engine", "Unlimited AI Queries", "Deadline automation suite", "Team collaboration tools", "Dedicated account support"]} />
        </div>
      </section>

      <section className="stitch-final-cta">
        <h2>Ready to master the regulatory landscape?</h2>
        <p>Join 500+ firms who use Resolven to stay compliant and agile in an ever-shifting market.</p>
        <div className="stitch-landing-actions">
          <a className="stitch-landing-button primary" href="#signin">Get Started for Free</a>
          <a className="stitch-landing-button secondary" href="mailto:hello@resolven.ai">Contact Sales</a>
        </div>
      </section>
    </main>
  );
}

function FeatureCard({
  icon,
  title,
  body,
  meta,
  extra,
}: {
  icon: string;
  title: string;
  body: string;
  meta?: string;
  extra?: string;
}) {
  return (
    <article className="stitch-feature-card">
      <MaterialIcon>{icon}</MaterialIcon>
      <h3>{title}</h3>
      <p>{body}</p>
      {meta ? <strong>{meta}</strong> : null}
      {extra ? <strong>{extra}</strong> : null}
    </article>
  );
}

function TierCard({
  eyebrow,
  title,
  price,
  cta,
  items,
  featured = false,
}: {
  eyebrow: string;
  title: string;
  price: string;
  cta: string;
  items: string[];
  featured?: boolean;
}) {
  return (
    <article className={`stitch-tier-card ${featured ? "featured" : ""}`}>
      <span>{eyebrow}</span>
      <h3>{title}</h3>
      <strong>{price} <small>/month</small></strong>
      <ul>
        {items.map((item) => (
          <li key={item}>
            <MaterialIcon>check_circle</MaterialIcon>
            {item}
          </li>
        ))}
      </ul>
      <a className="stitch-landing-button primary full" href="#signin">{cta}</a>
    </article>
  );
}
