import { AlertTriangle, RefreshCw } from "lucide-react";

export function ErrorState({
  title = "Something went wrong",
  error,
  onRetry,
}: {
  title?: string;
  error?: unknown;
  onRetry?: () => void;
}) {
  const message =
    error instanceof Error ? error.message : "The data could not be loaded. Please try again.";
  return (
    <div className="state-block error">
      <AlertTriangle size={22} />
      <h3>{title}</h3>
      <p>{message}</p>
      {onRetry ? (
        <button type="button" className="secondary-button" onClick={onRetry}>
          <RefreshCw size={16} /> Retry
        </button>
      ) : null}
    </div>
  );
}
