import { ArrowRight, FileSearch, Loader2, LockKeyhole, Network, ShieldCheck } from "lucide-react";

export function AuthScreen(props: {
  email: string;
  password: string;
  message: string;
  loading: boolean;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onSignIn: () => Promise<void>;
}) {
  return (
    <main className="auth-premium-screen">
      <section className="auth-premium-brand">
        <img className="auth-premium-logo" src="/logo_wordmark.png" alt="Resolven" />
        <div>
          <p className="auth-eyebrow">Regulatory intelligence workspace</p>
          <h1>
            Evidence-first monitoring for teams that live inside <em>regulation.</em>
          </h1>
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

      <form
        className="auth-premium-panel"
        aria-label="Sign in"
        onSubmit={(event) => {
          event.preventDefault();
          void props.onSignIn();
        }}
      >
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
            required
            disabled={props.loading}
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
            required
            disabled={props.loading}
          />
        </label>
        <button className="primary-button full auth-submit" type="submit" disabled={props.loading}>
          {props.loading ? (
            <>
              <Loader2 className="spin" size={16} />
              Signing in...
            </>
          ) : (
            <>
              Sign In
              <ArrowRight size={16} />
            </>
          )}
        </button>
        {props.message ? (
          <p className="notice auth-error" role="alert" aria-live="polite">
            {props.message}
          </p>
        ) : null}
        <p className="auth-security-note">
          <ShieldCheck size={15} />
          Your session is secured by Supabase during the identity migration.
        </p>
      </form>
    </main>
  );
}
