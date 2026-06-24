export function AuthScreen(props: {
  email: string;
  password: string;
  message: string;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onSignIn: () => void;
  onMagicLink: () => void;
  onDemo: () => void;
}) {
  return (
    <div className="auth-screen">
      <div className="auth-card">
        <img className="auth-wordmark" src="/logo_wordmark.png" alt="Resolven" />
        <h1>Resolven Regulatory AI</h1>
        <p>Sign in to monitor regulatory changes, deadlines, obligations, and stakeholder impact.</p>
        <input value={props.email} onChange={(event) => props.onEmail(event.target.value)} placeholder="Email" />
        <input
          value={props.password}
          onChange={(event) => props.onPassword(event.target.value)}
          placeholder="Password"
          type="password"
        />
        <button className="primary-button full" type="button" onClick={props.onSignIn}>
          Sign In
        </button>
        <button className="secondary-button full" type="button" onClick={props.onMagicLink}>
          Send Magic Link
        </button>
        <button className="ghost-button full" type="button" onClick={props.onDemo}>
          Continue Local Preview
        </button>
        {props.message ? <p className="notice">{props.message}</p> : null}
      </div>
    </div>
  );
}
