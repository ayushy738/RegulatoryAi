import { ArrowRight, FileSearch, LockKeyhole, Network, ShieldCheck } from "lucide-react";

export function AuthScreen(props: {
  email: string;
  password: string;
  message: string;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onSignIn: () => void;
}) {
  return (
    <main className="auth-premium-screen">
      <section className="auth-premium-brand">
        <img className="auth-premium-logo" src="/logo_wordmark.png" alt="Resolven" />
        <div>
          <p className="auth-eyebrow">Regulatory intelligence workspace</p>
          <h1>Evidence-first monitoring for teams that live inside regulation.</h1>
          <p>
            Track official updates, deadlines, obligations, stakeholders, and source evidence in one calm
            operational surface.
          </p>
        </div>
        <div className="auth-signal-grid">
          <span>
            <ShieldCheck size={18} />
            Official source always wins
          </span>
          <span>
            <FileSearch size={18} />
            Explainable regulatory answers
          </span>
          <span>
            <Network size={18} />
            Graph-backed impact context
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
          <LockKeyhole size={21} />
          <div>
            <h2>Sign in</h2>
            <p>Use your production Resolven credentials.</p>
          </div>
        </div>
        <label>
          Email
          <input
            value={props.email}
            onChange={(event) => props.onEmail(event.target.value)}
            placeholder="analyst@company.com"
            type="email"
            autoComplete="email"
          />
        </label>
        <label>
          Password
          <input
            value={props.password}
            onChange={(event) => props.onPassword(event.target.value)}
            placeholder="Enter password"
            type="password"
            autoComplete="current-password"
          />
        </label>
        <button className="primary-button full auth-submit" type="button" onClick={props.onSignIn}>
          Sign In
          <ArrowRight size={16} />
        </button>
        {props.message ? <p className="notice">{props.message}</p> : null}
      </section>
    </main>
  );
}
