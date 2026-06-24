import { Bell, CheckCircle2, Loader2 } from "lucide-react";

import { ErrorState } from "@/app/components/ui/ErrorState";
import { LoadingState } from "@/app/components/ui/LoadingState";
import { Panel } from "@/app/components/ui/Panel";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

export function NotificationsView() {
  const { settings, setSettings, sources, busyAction, handleSaveSettings, subscriptionsStatus } =
    useWorkspace();

  if (subscriptionsStatus.isLoading) {
    return <LoadingState label="Loading notification preferences..." />;
  }
  if (subscriptionsStatus.isError) {
    return (
      <ErrorState
        title="Unable to load preferences"
        error={subscriptionsStatus.error}
        onRetry={subscriptionsStatus.refetch}
      />
    );
  }

  return (
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
          Stakeholders and topics
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
          Email frequency
          <select
            value={settings.frequency}
            onChange={(event) =>
              setSettings({ ...settings, frequency: event.target.value as "daily" | "instant" })
            }
          >
            <option value="daily">Daily</option>
            <option value="instant">Instant</option>
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
        <button
          className="primary-button"
          type="button"
          onClick={() => void handleSaveSettings()}
          disabled={busyAction === "settings"}
        >
          {busyAction === "settings" ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />} Save
        </button>
      </div>
    </Panel>
  );
}
