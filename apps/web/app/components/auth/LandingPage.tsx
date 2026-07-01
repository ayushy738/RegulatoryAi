import Link from "next/link";
import { ArrowRight, Bell, CalendarClock, FileText, ShieldCheck } from "lucide-react";

export function LandingPage({
  canRead,
  email,
  password,
  authMessage,
  onEmail,
  onPassword,
  onSignIn,
}: {
  canRead: boolean;
  email: string;
  password: string;
  authMessage: string;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onSignIn: () => void;
}) {
  return (
    <main className="auth-premium-screen landing-mode">
      <section className="auth-premium-brand">
        <img className="auth-premium-logo" src="/logo_wordmark.png" alt="Resolven" />
        <div>
          <p className="auth-eyebrow">Resolven Regulatory AI</p>
          <h1>Know what changed, why it matters, and what to do next.</h1>
          <p>
            A focused regulatory intelligence workspace for analysts, compliance officers, legal teams,
            power producers, DISCOMs, transmission companies, and administrators.
          </p>
        </div>
        <div className="auth-signal-grid">
          <span>
            <ShieldCheck size={18} />
            Evidence before AI
          </span>
          <span>
            <CalendarClock size={18} />
            Deadlines surfaced automatically
          </span>
          <span>
            <Bell size={18} />
            Topic alerts and notifications
          </span>
        </div>
        <div className="auth-visualization" aria-hidden="true">
          <div className="auth-viz-row strong" />
          <div className="auth-viz-row" />
          <div className="auth-viz-row short" />
          <div className="auth-viz-nodes">
            <span />
            <span />
            <span />
          </div>
        </div>
      </section>

      <section className="auth-premium-panel" aria-label="Sign in">
        <div className="auth-card-header">
          <FileText size={21} />
          <div>
            <h2>{canRead ? "Workspace ready" : "Sign in"}</h2>
            <p>{canRead ? "Continue to the analyst workspace." : "Use your production Resolven credentials."}</p>
          </div>
        </div>
        {canRead ? (
          <Link className="primary-button full auth-submit" href="/latest">
            Open Workspace
            <ArrowRight size={16} />
          </Link>
        ) : (
          <>
            <label>
              Email
              <input
                value={email}
                onChange={(event) => onEmail(event.target.value)}
                placeholder="analyst@company.com"
                type="email"
                autoComplete="email"
              />
            </label>
            <label>
              Password
              <input
                value={password}
                onChange={(event) => onPassword(event.target.value)}
                placeholder="Enter password"
                type="password"
                autoComplete="current-password"
              />
            </label>
            <button className="primary-button full auth-submit" type="button" onClick={onSignIn}>
              Sign In
              <ArrowRight size={16} />
            </button>
          </>
        )}
        {authMessage ? <p className="notice">{authMessage}</p> : null}
      </section>
    </main>
  );
}
