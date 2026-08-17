"use client";

import { Bell, Check } from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { Button } from "@/app/components/ui/Button";
import { CheckboxField } from "@/app/components/ui/Field";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { ErrorState } from "@/app/components/ui/ErrorState";
import { PageHeader, SectionHeader } from "@/app/components/ui/PageHeader";
import { SkeletonCards } from "@/app/components/ui/Skeleton";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

const TOPIC_OPTIONS = [
  "Tariffs",
  "Solar",
  "Wind",
  "Transmission",
  "Consultations",
  "Compliance",
];

/**
 * Subscription configuration, on its own page rather than crammed into the
 * notification drawer. Sections are ordered by decision: whether to receive
 * email at all, then what to receive it about.
 */
export function NotificationsView() {
  const {
    settings,
    setSettings,
    catalogSources,
    busyAction,
    handleSaveSettings,
    subscriptionsStatus,
  } = useWorkspace();

  if (subscriptionsStatus.isLoading) {
    return (
      <div className="rv-page rv-page--reading">
        <PageHeader eyebrow="Account" title="Notification preferences" />
        <SkeletonCards count={3} lines={3} label="Loading notification preferences" />
      </div>
    );
  }

  if (subscriptionsStatus.isError) {
    return (
      <div className="rv-page rv-page--reading">
        <PageHeader eyebrow="Account" title="Notification preferences" />
        <ErrorState
          title="Unable to load preferences"
          body="We couldn't retrieve your notification settings."
          error={subscriptionsStatus.error}
          onRetry={subscriptionsStatus.refetch}
        />
      </div>
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
      const next = catalogSources
        .map((source) => source.id)
        .filter((id) => id !== sourceId);
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

  function toggleTopic(topic: string) {
    const current = new Set(settings.topics);
    if (current.has(topic)) current.delete(topic);
    else current.add(topic);
    setSettings({ ...settings, topics: Array.from(current), frequency: "instant" });
  }

  return (
    <div className="rv-page rv-page--reading">
      <PageHeader
        eyebrow="Account"
        title="Notification preferences"
        description="Choose how and when Resolven tells you about regulatory activity. In-app notifications always stay on."
      />

      <section className="rv-section">
        <SectionHeader title="Email alerts" />
        <div className="rv-card">
          <CheckboxField
            label="Email me regulatory updates"
            hint="One email per new or changed regulatory update from your selected sources."
            checked={settings.email_enabled}
            onChange={(checked) =>
              setSettings({
                ...settings,
                email_enabled: checked,
                frequency: "instant",
              })
            }
          />
          <div className="rv-inline-fact">
            <span className="rv-fact__label">Frequency</span>
            <Badge tone="info">Instant</Badge>
            <span className="rv-helper">
              Digest scheduling is not available yet; alerts are delivered as they are
              detected.
            </span>
          </div>
        </div>
      </section>

      <section className="rv-section">
        <SectionHeader
          title="Sources"
          count={allSourcesSelected ? "All" : `${settings.source_ids.length}`}
        />
        <div className="rv-card">
          <CheckboxField
            label="All sources"
            hint="Follow every regulator Resolven monitors, including ones added later."
            checked={allSourcesSelected}
            onChange={(checked) => {
              setSettings({
                ...settings,
                source_ids: checked ? [] : catalogSources.map((source) => source.id),
                frequency: "instant",
              });
            }}
          />
          {catalogSources.length ? (
            <div className="rv-option-grid">
              {catalogSources.map((source) => (
                <CheckboxField
                  key={source.id}
                  label={source.name}
                  checked={allSourcesSelected || settings.source_ids.includes(source.id)}
                  onChange={() => toggleSource(source.id)}
                />
              ))}
            </div>
          ) : (
            <EmptyState
              compact
              title="No sources available yet"
              body="Once regulators are registered and enabled, they appear here for subscription."
              Icon={Bell}
            />
          )}
        </div>
      </section>

      <section className="rv-section">
        <SectionHeader title="Topics" />
        <div className="rv-card">
          <p className="rv-helper">
            Topics narrow which updates are treated as mentions. Leave them all off to be
            notified about everything from your selected sources.
          </p>
          <div className="rv-option-grid">
            {TOPIC_OPTIONS.map((topic) => (
              <CheckboxField
                key={topic}
                label={topic}
                checked={settings.topics.includes(topic)}
                onChange={() => toggleTopic(topic)}
              />
            ))}
          </div>
        </div>
      </section>

      <section className="rv-section">
        <div className="rv-card">
          <p className="notification-preference-summary rv-helper">
            Email notifications: {settings.email_enabled ? "ON" : "OFF"}
            <br />
            Sources: {selectedNames}
            <br />
            Frequency: Instant
          </p>
          <div className="rv-page-header__actions">
            <Button
              variant="primary"
              Icon={Check}
              loading={busyAction === "settings"}
              onClick={() => void handleSaveSettings()}
            >
              Save preferences
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
