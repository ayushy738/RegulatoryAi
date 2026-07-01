import { Bell, CheckCircle2, Loader2, Mail } from "lucide-react";

import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { Panel } from "@/app/components/ui/Panel";
import { clampText, formatDate } from "@/app/workspace/format";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function NotificationsView() {
  const {
    settings,
    setSettings,
    sources,
    events,
    digestDate,
    busyAction,
    handleSaveSettings,
    subscriptionsStatus,
  } = useWorkspace();

  if (subscriptionsStatus.isLoading) return <LoadingState label="Loading notification preferences..." />;
  if (subscriptionsStatus.isError) {
    return (
      <ErrorState title="Unable to load preferences" error={subscriptionsStatus.error} onRetry={subscriptionsStatus.refetch} />
    );
  }

  return (
    <div className="two-column ops-page">
      <Panel title="Notification Preferences" icon={Bell}>
        <div className="settings-grid">
          <label>
            Sources
            <select
              value={settings.source_ids[0] ?? ""}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  source_ids: event.target.value ? [Number(event.target.value)] : [],
                })
              }
            >
              <option value="">All sources</option>
              {sources.map((source) => (
                <option key={source.id} value={source.id}>
                  {source.name}
                </option>
              ))}
            </select>
          </label>
          <label>
            Topics
            <input
              value={settings.topics.join(", ")}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  topics: event.target.value
                    .split(",")
                    .map((item) => item.trim())
                    .filter(Boolean),
                })
              }
            />
          </label>
          <label>
            Frequency
            <select
              value={settings.frequency}
              onChange={(event) => setSettings({ ...settings, frequency: event.target.value as "daily" | "instant" })}
            >
              <option value="daily">Daily digest</option>
              <option value="instant">Instant alerts</option>
            </select>
          </label>
          <label className="toggle-line">
            <input
              type="checkbox"
              checked={settings.email_enabled}
              onChange={(event) => setSettings({ ...settings, email_enabled: event.target.checked })}
            />
            Email alerts enabled
          </label>
          <div className="topic-chip-row">
            {settings.topics.map((topic) => (
              <button
                key={topic}
                type="button"
                onClick={() => setSettings({ ...settings, topics: settings.topics.filter((item) => item !== topic) })}
              >
                {topic}
              </button>
            ))}
          </div>
          <button
            className="primary-button"
            type="button"
            onClick={() => void handleSaveSettings()}
            disabled={busyAction === "settings"}
          >
            {busyAction === "settings" ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />}
            Save preferences
          </button>
        </div>
      </Panel>

      <Panel title="Digest Preview" icon={Mail}>
        <div className="digest-preview">
          <span>{formatDate(digestDate)}</span>
          <h3>{settings.frequency === "instant" ? "Instant regulatory alert" : "Daily regulatory digest"}</h3>
          <p>{settings.email_enabled ? "Email delivery enabled" : "Email delivery paused"}</p>
          {events.slice(0, 5).map((event) => (
            <article key={event.id}>
              <strong>{event.title}</strong>
              <p>{clampText(event.summary?.plain_english_summary ?? event.raw_summary, 130)}</p>
            </article>
          ))}
          {!events.length ? <p className="muted">No events are available to preview.</p> : null}
        </div>
      </Panel>
    </div>
  );
}
