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
    catalogSources,
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

  const allSourcesSelected = settings.source_ids.length === 0;
  const selectedNames = allSourcesSelected
    ? "All sources"
    : catalogSources
        .filter((source) => settings.source_ids.includes(source.id))
        .map((source) => source.name)
        .join(", ") || "No sources selected";

  function toggleSource(sourceId: number) {
    if (allSourcesSelected) {
      const next = catalogSources.map((source) => source.id).filter((id) => id !== sourceId);
      setSettings({ ...settings, source_ids: next, frequency: "instant" });
      return;
    }
    const current = new Set(settings.source_ids);
    if (current.has(sourceId)) current.delete(sourceId);
    else current.add(sourceId);
    setSettings({
      ...settings,
      source_ids: Array.from(current),
      frequency: "instant",
    });
  }

  return (
    <div className="two-column ops-page">
      <Panel title="Notification Preferences" icon={Bell}>
        <div className="settings-grid">
          <label className="toggle-line">
            <input
              type="checkbox"
              checked={settings.email_enabled}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  email_enabled: event.target.checked,
                  frequency: "instant",
                })
              }
            />
            Email me regulatory updates
          </label>

          <div>
            <strong>Frequency</strong>
            <p className="muted">Instant — one email per new or changed regulatory update.</p>
          </div>

          <div className="source-subscriptions">
            <strong>Sources</strong>
            <label className="source-subscription-option">
              <input
                type="checkbox"
                checked={allSourcesSelected}
                onChange={(event) => {
                  if (event.target.checked) {
                    setSettings({ ...settings, source_ids: [], frequency: "instant" });
                    return;
                  }
                  setSettings({
                    ...settings,
                    source_ids: catalogSources.map((source) => source.id),
                    frequency: "instant",
                  });
                }}
              />
              All sources
            </label>
            {catalogSources.map((source) => (
              <label key={source.id} className="source-subscription-option">
                <input
                  type="checkbox"
                  checked={allSourcesSelected || settings.source_ids.includes(source.id)}
                  onChange={() => toggleSource(source.id)}
                />
                {source.name}
              </label>
            ))}
          </div>

          <p className="notification-preference-summary">
            Email notifications: {settings.email_enabled ? "ON" : "OFF"}
            <br />
            Sources: {selectedNames}
            <br />
            Frequency: Instant
          </p>

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

      <Panel title="Recent updates preview" icon={Mail}>
        <div className="digest-preview">
          <span>{formatDate(digestDate)}</span>
          <h3>Instant regulatory alert</h3>
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
