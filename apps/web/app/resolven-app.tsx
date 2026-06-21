"use client";

import type { Session } from "@supabase/supabase-js";
import {
  Bell,
  Bookmark,
  BookOpenText,
  CheckCircle2,
  ClipboardList,
  Database,
  Download,
  ExternalLink,
  FileJson,
  FileSpreadsheet,
  FileText,
  History,
  Loader2,
  LogOut,
  MessageSquareText,
  RadioTower,
  RefreshCw,
  Search,
  Send,
  Star,
  UserCircle,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type {
  CrawlRun,
  DigestEvent,
  SourceHealth,
  SubscriptionSettings,
  SystemDocument,
} from "@/lib/api";
import {
  downloadLatestExport,
  getHealth,
  getDoc,
  getEvent,
  getEvents,
  getLatestDigest,
  getRuns,
  getSources,
  getSubscriptions,
  markRead,
  saveSubscriptions,
  sendChat,
  toggleBookmark,
  toggleSource,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

type RouteKey =
  | "today"
  | "browse"
  | "saved"
  | "event"
  | "notifications"
  | "account"
  | "admin-sources"
  | "admin-runs"
  | "api-docs"
  | "flow";

type NavItem = {
  href: string;
  label: string;
  route: RouteKey;
  Icon: LucideIcon;
  admin?: boolean;
};

const navItems: NavItem[] = [
  { href: "/", label: "Today", route: "today", Icon: ClipboardList },
  { href: "/browse", label: "Browse", route: "browse", Icon: Search },
  { href: "/saved", label: "Saved", route: "saved", Icon: Star },
  { href: "/notifications", label: "Notifications", route: "notifications", Icon: Bell },
  { href: "/account", label: "Account", route: "account", Icon: UserCircle },
  { href: "/admin/sources", label: "Sources", route: "admin-sources", Icon: Database, admin: true },
  { href: "/admin/runs", label: "Runs", route: "admin-runs", Icon: History, admin: true },
  { href: "/api-docs", label: "API docs", route: "api-docs", Icon: BookOpenText },
  { href: "/flow", label: "Flow", route: "flow", Icon: RadioTower },
];

const defaultSettings: SubscriptionSettings = {
  jurisdictions: ["central"],
  source_ids: [],
  topics: ["solar", "tariff", "open access", "RPO/REC", "storage", "transmission"],
  email_enabled: true,
  frequency: "daily",
};

const topicOptions = ["all", "solar", "tariff", "open access", "RPO/REC", "storage", "transmission"];
const jurisdictionOptions = ["all", "central", "state"];

export function ResolvenApp({
  initialRoute,
  initialEventId,
}: {
  initialRoute: RouteKey;
  initialEventId?: number;
}) {
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [events, setEvents] = useState<DigestEvent[]>([]);
  const [archiveEvents, setArchiveEvents] = useState<DigestEvent[]>([]);
  const [selected, setSelected] = useState<DigestEvent | null>(null);
  const [digestDate, setDigestDate] = useState("");
  const [query, setQuery] = useState("");
  const [topic, setTopic] = useState("all");
  const [jurisdiction, setJurisdiction] = useState("all");
  const [chatInput, setChatInput] = useState("");
  const [chatReply, setChatReply] = useState("");
  const [chatLoading, setChatLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [settings, setSettings] = useState<SubscriptionSettings>(defaultSettings);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [doc, setDoc] = useState<SystemDocument | null>(null);
  const [pipelineStatus, setPipelineStatus] = useState<"online" | "degraded" | "offline">("offline");
  const [isAdmin, setIsAdmin] = useState(false);

  const token = session?.access_token;
  const canRead = Boolean(token || demoMode);
  const userEmail = session?.user.email ?? (demoMode ? "local-preview@resolven.ai" : "");

  useEffect(() => {
    if (!supabase) {
      setDemoMode(true);
      setAuthReady(true);
      return;
    }
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setAuthReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      setSession(nextSession);
      setAuthReady(true);
    });
    return () => data.subscription.unsubscribe();
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setQuery(params.get("q") ?? "");
    setTopic(params.get("topic") ?? "all");
    setJurisdiction(params.get("jurisdiction") ?? "all");
  }, []);

  useEffect(() => {
    if (!canRead || !authReady) {
      setLoading(false);
      return;
    }
    void loadBaseData();
  }, [canRead, authReady]);

  useEffect(() => {
    if (!canRead || initialRoute !== "browse") return;
    const params = new URLSearchParams();
    if (query) params.set("q", query);
    if (topic !== "all") params.set("topic", topic);
    if (jurisdiction !== "all") params.set("jurisdiction", jurisdiction);
    window.history.replaceState(null, "", params.toString() ? `/browse?${params}` : "/browse");
    void loadArchive();
  }, [query, topic, jurisdiction, canRead, initialRoute]);

  useEffect(() => {
    if (!canRead) return;
    if (initialRoute === "event" && initialEventId) {
      getEvent(initialEventId, token)
        .then((event) => setSelected(event))
        .catch((error) => setStatusMessage(error.message));
    }
    if (initialRoute === "admin-sources") {
      getSources(token).then(setSources).catch((error) => setStatusMessage(error.message));
    }
    if (initialRoute === "admin-runs") {
      getRuns(token).then(setRuns).catch((error) => setStatusMessage(error.message));
    }
    if (initialRoute === "api-docs") {
      getDoc("backend-api", token).then(setDoc).catch((error) => setStatusMessage(error.message));
    }
    if (initialRoute === "flow") {
      getDoc("complete-flow", token).then(setDoc).catch((error) => setStatusMessage(error.message));
    }
  }, [initialRoute, initialEventId, canRead, token]);

  async function loadBaseData() {
    setLoading(true);
    setStatusMessage("");
    try {
      const [digest, subscription, healthRes] = await Promise.all([
        getLatestDigest(token),
        getSubscriptions(token).catch(() => defaultSettings),
        getHealth().catch(() => null),
      ]);
      setEvents(digest.events);
      setArchiveEvents(digest.events);
      setDigestDate(digest.digest_date);
      setSelected((current) => current ?? digest.events[0] ?? null);
      setSettings(subscription);
      if (healthRes) {
        setPipelineStatus(healthRes.database_connected ? "online" : "degraded");
      }
      getSources(token)
        .then(() => setIsAdmin(true))
        .catch(() => setIsAdmin(false));
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to load briefing.");
      setPipelineStatus("offline");
    } finally {
      setLoading(false);
    }
  }

  async function loadArchive() {
    try {
      const loaded = await getEvents(token, { query, topic, jurisdiction });
      setArchiveEvents(loaded);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to load archive.");
    }
  }

  async function signIn() {
    if (!supabase) {
      setDemoMode(true);
      return;
    }
    setAuthMessage("");
    if (!email.trim()) {
      setAuthMessage("Enter your email address.");
      return;
    }
    if (password) {
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      setAuthMessage(error ? error.message : "");
      return;
    }
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    setAuthMessage(error ? error.message : "Check your email for the secure sign-in link.");
  }

  async function signOut() {
    await supabase?.auth.signOut();
    setDemoMode(false);
    setSession(null);
    setEvents([]);
    setArchiveEvents([]);
    setSelected(null);
  }

  async function askQuestion(event: DigestEvent | null = selected) {
    if (!event || !chatInput.trim()) return;
    setChatLoading(true);
    setChatReply("");
    try {
      const response = await sendChat(chatInput, event.id, token);
      setChatReply(response.reply);
    } catch (error) {
      setChatReply(error instanceof Error ? error.message : "Chat request failed. Please try again.");
    } finally {
      setChatLoading(false);
    }
  }

  async function markEventRead(event: DigestEvent) {
    await markRead(event.id, token);
    updateEvent(event.id, { is_read: true });
  }

  async function bookmarkEvent(event: DigestEvent) {
    const response = await toggleBookmark(event.id, token);
    updateEvent(event.id, { is_bookmarked: response.is_bookmarked });
  }

  function updateEvent(eventId: number, patch: Partial<DigestEvent>) {
    const update = (item: DigestEvent) => (item.id === eventId ? { ...item, ...patch } : item);
    setEvents((items) => items.map(update));
    setArchiveEvents((items) => items.map(update));
    setSelected((current) => (current?.id === eventId ? { ...current, ...patch } : current));
  }

  async function savePrefs() {
    try {
      const saved = await saveSubscriptions(settings, token);
      setSettings(saved);
      setStatusMessage("Notification settings saved.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Settings save failed.");
    }
  }

  async function exportLatest(format: "json" | "csv" | "markdown") {
    try {
      await downloadLatestExport(format, token);
      setStatusMessage(`Latest news exported as ${format}.`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Export failed.");
    }
  }

  async function handleSourceToggle(source: SourceHealth) {
    const result = await toggleSource(source.id, token);
    setSources((items) =>
      items.map((item) => (item.id === source.id ? { ...item, enabled: result.enabled } : item)),
    );
  }

  const activeEvents = useMemo(() => {
    const source = initialRoute === "browse" ? archiveEvents : events;
    return source.filter((event) => {
      const haystack = `${event.title} ${event.issuing_body ?? ""} ${event.topic_tags.join(" ")}`.toLowerCase();
      const matchesText = !query || haystack.includes(query.toLowerCase());
      const matchesTopic = topic === "all" || event.topic_tags.includes(topic);
      const matchesJurisdiction = jurisdiction === "all" || event.jurisdiction === jurisdiction;
      return matchesText && matchesTopic && matchesJurisdiction;
    });
  }, [archiveEvents, events, initialRoute, jurisdiction, query, topic]);

  const savedEvents = useMemo(
    () => [...events, ...archiveEvents].filter((event, index, all) => {
      return event.is_bookmarked && all.findIndex((item) => item.id === event.id) === index;
    }),
    [archiveEvents, events],
  );

  if (!authReady) return <FullPageStatus title="Resolven Regulatory AI" body="Preparing secure session..." />;

  if (!canRead) {
    return (
      <main className="auth-screen">
        <section className="auth-card">
          <img src="/logo_wordmark.png" alt="Resolven" className="auth-wordmark" />
          <p className="eyebrow">Energy regulatory intelligence</p>
          <h1>Resolven Regulatory AI</h1>
          <p className="muted">A calm daily briefing for Indian energy regulatory changes.</p>
          <div className="auth-form">
            <input value={email} onChange={(event) => setEmail(event.target.value)} placeholder="Email" type="email" />
            <input
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              placeholder="Password, optional for magic link"
              type="password"
            />
            <button onClick={signIn} className="primary-action">Continue</button>
            <button onClick={() => setDemoMode(true)} className="secondary-action">Preview local data</button>
            {authMessage ? <p className="form-note">{authMessage}</p> : null}
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="app-frame">
      <aside className="rail">
        <a href="/" className="brand-lockup" aria-label="Resolven Regulatory AI home">
          <img src="/logo_mark.png" alt="" />
          <span>
            <strong>Resolven</strong>
            <small>Regulatory AI</small>
          </span>
        </a>
        <nav className="rail-nav" aria-label="Primary navigation">
          {navItems.filter((item) => !item.admin || isAdmin).map((item) => (
            <a key={item.href} href={item.href} className={item.route === initialRoute ? "active" : ""}>
              <item.Icon size={18} aria-hidden />
              <span>{item.label}</span>
            </a>
          ))}
        </nav>
        <div className="rail-footer">
          <span className={`health-dot ${pipelineStatus === "online" ? "" : pipelineStatus === "degraded" ? "degraded" : "offline"}`} />
          <span>Pipeline {pipelineStatus}</span>
        </div>
        <button onClick={signOut} className="sign-out">
          <LogOut size={18} aria-hidden />
          <span>Sign out</span>
        </button>
      </aside>

      <section className="workspace">
        <header className="topbar">
          <div>
            <p className="eyebrow">Resolven Regulatory AI</p>
            <h1>{routeTitle(initialRoute)}</h1>
          </div>
          <div className="topbar-actions">
            <span className="user-chip">{userEmail}</span>
            <button onClick={() => void loadBaseData()} title="Refresh data" className="icon-button">
              <RefreshCw size={18} aria-hidden />
            </button>
          </div>
        </header>

        {statusMessage ? <div className="notice">{statusMessage}</div> : null}

        {initialRoute === "today" ? (
          <TodayScreen
            digestDate={digestDate}
            events={activeEvents}
            loading={loading}
            selected={selected}
            onSelect={setSelected}
            onRead={markEventRead}
            onBookmark={bookmarkEvent}
            onAsk={askQuestion}
            chatInput={chatInput}
            setChatInput={setChatInput}
            chatReply={chatReply}
            chatLoading={chatLoading}
            onExport={exportLatest}
          />
        ) : null}

        {initialRoute === "browse" ? (
          <BrowseScreen
            events={activeEvents}
            query={query}
            setQuery={setQuery}
            topic={topic}
            setTopic={setTopic}
            jurisdiction={jurisdiction}
            setJurisdiction={setJurisdiction}
          />
        ) : null}

        {initialRoute === "saved" ? (
          <SavedScreen events={savedEvents} onBookmark={bookmarkEvent} />
        ) : null}

        {initialRoute === "event" ? (
          <EventDetailScreen
            event={selected}
            chatInput={chatInput}
            setChatInput={setChatInput}
            chatReply={chatReply}
            onAsk={askQuestion}
            onRead={markEventRead}
            onBookmark={bookmarkEvent}
          />
        ) : null}

        {initialRoute === "notifications" ? (
          <NotificationsScreen settings={settings} setSettings={setSettings} onSave={savePrefs} preview={events[0]} />
        ) : null}

        {initialRoute === "account" ? (
          <AccountScreen email={userEmail} demoMode={demoMode} onSignOut={signOut} />
        ) : null}

        {initialRoute === "admin-sources" ? (
          <SourcesScreen sources={sources} onRefresh={() => getSources(token).then(setSources)} onToggle={handleSourceToggle} />
        ) : null}

        {initialRoute === "admin-runs" ? (
          <RunsScreen runs={runs} onRefresh={() => getRuns(token).then(setRuns)} />
        ) : null}

        {initialRoute === "api-docs" || initialRoute === "flow" ? (
          <DocsScreen doc={doc} />
        ) : null}
      </section>
    </main>
  );
}

function TodayScreen(props: {
  digestDate: string;
  events: DigestEvent[];
  loading: boolean;
  selected: DigestEvent | null;
  onSelect: (event: DigestEvent) => void;
  onRead: (event: DigestEvent) => Promise<void>;
  onBookmark: (event: DigestEvent) => Promise<void>;
  onAsk: (event?: DigestEvent | null) => Promise<void>;
  chatInput: string;
  setChatInput: (value: string) => void;
  chatReply: string;
  chatLoading?: boolean;
  onExport: (format: "json" | "csv" | "markdown") => Promise<void>;
}) {
  const sourceCount = new Set(props.events.map((event) => event.issuing_body).filter(Boolean)).size;
  return (
    <div className="today-grid">
      <section className="briefing-column">
        <div className="briefing-header">
          <div>
            <p className="eyebrow">Today - {props.digestDate || "latest run"}</p>
            <h2>{props.events.length} updates across {sourceCount || 0} bodies</h2>
          </div>
          <ExportButtons onExport={props.onExport} />
        </div>
        {props.loading ? <SkeletonList /> : null}
        {!props.loading && props.events.length === 0 ? <EmptyState title="No updates loaded" body="Refresh the briefing or run the pipeline." /> : null}
        <div className="event-list">
          {props.events.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              active={props.selected?.id === event.id}
              onSelect={() => props.onSelect(event)}
              onRead={() => props.onRead(event)}
              onBookmark={() => props.onBookmark(event)}
            />
          ))}
        </div>
      </section>
      <aside className="insight-panel">
        <EventDetailCompact event={props.selected} />
        <InsightChat
          event={props.selected}
          chatInput={props.chatInput}
          setChatInput={props.setChatInput}
          chatReply={props.chatReply}
          chatLoading={props.chatLoading}
          onAsk={() => props.onAsk(props.selected)}
        />
      </aside>
    </div>
  );
}

function BrowseScreen(props: {
  events: DigestEvent[];
  query: string;
  setQuery: (value: string) => void;
  topic: string;
  setTopic: (value: string) => void;
  jurisdiction: string;
  setJurisdiction: (value: string) => void;
}) {
  return (
    <section className="content-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Archive</p>
          <h2>Browse all regulatory updates</h2>
        </div>
      </div>
      <div className="filter-bar">
        <label>
          <Search size={18} aria-hidden />
          <input value={props.query} onChange={(event) => props.setQuery(event.target.value)} placeholder="Search title, source, topic" />
        </label>
        <select value={props.topic} onChange={(event) => props.setTopic(event.target.value)}>
          {topicOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <select value={props.jurisdiction} onChange={(event) => props.setJurisdiction(event.target.value)}>
          {jurisdictionOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
      </div>
      <div className="event-list">
        {props.events.map((event) => <EventCard key={event.id} event={event} />)}
      </div>
    </section>
  );
}

function SavedScreen({ events, onBookmark }: { events: DigestEvent[]; onBookmark: (event: DigestEvent) => Promise<void> }) {
  return (
    <section className="content-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Working set</p>
          <h2>Saved updates</h2>
        </div>
      </div>
      {events.length === 0 ? (
        <EmptyState title="Nothing saved yet" body="Use the bookmark control on any update to keep it here." />
      ) : (
        <div className="event-list">
          {events.map((event) => <EventCard key={event.id} event={event} onBookmark={() => onBookmark(event)} />)}
        </div>
      )}
    </section>
  );
}

function EventDetailScreen(props: {
  event: DigestEvent | null;
  chatInput: string;
  setChatInput: (value: string) => void;
  chatReply: string;
  onAsk: (event?: DigestEvent | null) => Promise<void>;
  onRead: (event: DigestEvent) => Promise<void>;
  onBookmark: (event: DigestEvent) => Promise<void>;
}) {
  if (!props.event) return <EmptyState title="Event not found" body="Open an update from Today or Browse." />;
  return (
    <div className="detail-grid">
      <section className="content-card">
        <DocketStrip event={props.event} />
        <h2 className="detail-title">{props.event.title}</h2>
        <div className="detail-actions">
          <button onClick={() => props.onRead(props.event!)}><CheckCircle2 size={16} /> Mark read</button>
          <button onClick={() => props.onBookmark(props.event!)}><Bookmark size={16} /> Bookmark</button>
          <a href={String(props.event.source_url)} target="_blank" rel="noreferrer"><ExternalLink size={16} /> Source</a>
        </div>
        <SummaryBlock event={props.event} />
      </section>
      <InsightChat
        event={props.event}
        chatInput={props.chatInput}
        setChatInput={props.setChatInput}
        chatReply={props.chatReply}
        onAsk={() => props.onAsk(props.event)}
      />
    </div>
  );
}

function NotificationsScreen(props: {
  settings: SubscriptionSettings;
  setSettings: (value: SubscriptionSettings) => void;
  onSave: () => Promise<void>;
  preview?: DigestEvent;
}) {
  const updateTopics = (value: string) =>
    props.setSettings({ ...props.settings, topics: value.split(",").map((item) => item.trim()).filter(Boolean) });
  return (
    <section className="content-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Subscriptions</p>
          <h2>Notification settings</h2>
        </div>
        <button onClick={props.onSave} className="primary-action compact">Save changes</button>
      </div>
      <div className="settings-grid">
        <label className="switch-row">
          <span>Email me a daily digest</span>
          <input
            type="checkbox"
            checked={props.settings.email_enabled}
            onChange={(event) => props.setSettings({ ...props.settings, email_enabled: event.target.checked })}
          />
        </label>
        <label>
          Frequency
          <select
            value={props.settings.frequency}
            onChange={(event) =>
              props.setSettings({ ...props.settings, frequency: event.target.value as "daily" | "instant" })
            }
          >
            <option value="daily">Once daily</option>
            <option value="instant">As found</option>
          </select>
        </label>
        <label>
          Topics
          <input value={props.settings.topics.join(", ")} onChange={(event) => updateTopics(event.target.value)} />
        </label>
      </div>
      <div className="preview-box">
        <p className="eyebrow">Preview of a matching update</p>
        {props.preview ? <EventCard event={props.preview} /> : <p>No preview update is loaded yet.</p>}
      </div>
    </section>
  );
}

function AccountScreen({ email, demoMode, onSignOut }: { email: string; demoMode: boolean; onSignOut: () => Promise<void> }) {
  return (
    <section className="content-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Profile</p>
          <h2>Account</h2>
        </div>
        <button onClick={onSignOut} className="secondary-action compact">Sign out</button>
      </div>
      <dl className="definition-list">
        <dt>Email</dt>
        <dd>{email}</dd>
        <dt>Session mode</dt>
        <dd>{demoMode ? "Local preview" : "Supabase Auth"}</dd>
        <dt>Product</dt>
        <dd>Resolven Regulatory AI</dd>
      </dl>
    </section>
  );
}

function SourcesScreen(props: {
  sources: SourceHealth[];
  onRefresh: () => Promise<unknown>;
  onToggle: (source: SourceHealth) => Promise<void>;
}) {
  return (
    <section className="content-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Admin</p>
          <h2>Sources</h2>
        </div>
        <button onClick={() => void props.onRefresh()} className="secondary-action compact">Refresh</button>
      </div>
      <div className="table-like">
        <div className="table-row header"><span>Code</span><span>Name</span><span>Type</span><span>Health</span><span>Enabled</span></div>
        {props.sources.map((source) => (
          <div className="table-row" key={source.id}>
            <span className="mono">{source.code}</span>
            <span>{source.name}</span>
            <span>{source.crawler_type}</span>
            <span>{source.consecutive_failures ? `${source.consecutive_failures} failures` : "ok"}</span>
            <button onClick={() => void props.onToggle(source)}>{source.enabled ? "Enabled" : "Disabled"}</button>
          </div>
        ))}
      </div>
    </section>
  );
}

function RunsScreen({ runs, onRefresh }: { runs: CrawlRun[]; onRefresh: () => Promise<unknown> }) {
  return (
    <section className="content-card">
      <div className="section-header">
        <div>
          <p className="eyebrow">Admin</p>
          <h2>Pipeline runs</h2>
        </div>
        <button onClick={() => void onRefresh()} className="secondary-action compact">Refresh</button>
      </div>
      <div className="run-list">
        {runs.map((run) => (
          <article key={run.id} className="run-card">
            <strong>{run.status}</strong>
            <span>{new Date(run.started_at).toLocaleString()}</span>
            <span>{run.sources_succeeded}/{run.sources_attempted} sources</span>
            <span>{run.docs_found} docs - {run.new_events} new events</span>
            {run.errors.length ? <code>{JSON.stringify(run.errors)}</code> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function DocsScreen({ doc }: { doc: SystemDocument | null }) {
  if (!doc) return <FullPageStatus title="Documentation" body="Loading database-backed documentation..." />;
  return (
    <section className="content-card doc-card">
      <p className="eyebrow">{doc.category}</p>
      <h2>{doc.title}</h2>
      <MarkdownLite content={doc.content_md ?? ""} />
    </section>
  );
}

function EventCard({
  event,
  active,
  onSelect,
  onRead,
  onBookmark,
}: {
  event: DigestEvent;
  active?: boolean;
  onSelect?: () => void;
  onRead?: () => void;
  onBookmark?: () => void;
}) {
  const mainContent = (
    <>
      <DocketStrip event={event} />
      <h3>{event.title}</h3>
      <p>{event.summary?.plain_english_summary ?? event.raw_summary ?? "No summary available."}</p>
    </>
  );

  return (
    <article className={`event-card ${active ? "active" : ""}`}>
      {onSelect ? (
        <button onClick={onSelect} className="event-main">{mainContent}</button>
      ) : (
        <a href={`/events/${event.id}`} className="event-main">{mainContent}</a>
      )}
      <div className="card-footer">
        <div className="tag-row">{(event.topic_tags ?? []).slice(0, 4).map((tag) => <span key={tag}>{tag}</span>)}</div>
        <div className="card-actions">
          <button onClick={onRead} title="Mark read" disabled={!onRead}><CheckCircle2 size={16} /></button>
          <button onClick={onBookmark} title="Bookmark" disabled={!onBookmark} className={event.is_bookmarked ? "marked" : ""}>
            <Bookmark size={16} />
          </button>
          <a href={`/events/${event.id}`} title="Read and ask"><MessageSquareText size={16} /></a>
          <a href={String(event.source_url)} target="_blank" rel="noreferrer" title="Open source"><ExternalLink size={16} /></a>
        </div>
      </div>
    </article>
  );
}

function DocketStrip({ event }: { event: DigestEvent }) {
  return (
    <p className={`docket ${event.event_type.toLowerCase()}`}>
      <span>{(event.jurisdiction ?? "unknown").toUpperCase()}</span>
      <span>{event.issuing_body ?? "Unknown body"}</span>
      <span>{event.issue_date ?? "date unknown"}</span>
      <span>{event.event_type}</span>
    </p>
  );
}

function SummaryBlock({ event }: { event: DigestEvent }) {
  return (
    <div className="summary-block">
      <h3>Grounded summary</h3>
      <p>{event.summary?.plain_english_summary ?? event.raw_summary ?? "No summary stored for this event."}</p>
      <h3>Why it matters</h3>
      <p>{event.summary?.why_it_matters ?? "Not specified in the stored event text."}</p>
      <div className="tag-row">{(event.summary?.affected_segments ?? event.topic_tags ?? []).map((tag) => <span key={tag}>{tag}</span>)}</div>
    </div>
  );
}

function EventDetailCompact({ event }: { event: DigestEvent | null }) {
  if (!event) return <EmptyState title="Select an update" body="Choose an event from the briefing to inspect it." />;
  return (
    <section className="detail-compact">
      <DocketStrip event={event} />
      <h2>{event.title}</h2>
      <SummaryBlock event={event} />
    </section>
  );
}

function InsightChat({
  event,
  chatInput,
  setChatInput,
  chatReply,
  chatLoading,
  onAsk,
}: {
  event: DigestEvent | null;
  chatInput: string;
  setChatInput: (value: string) => void;
  chatReply: string;
  chatLoading?: boolean;
  onAsk: () => Promise<void>;
}) {
  const prompts = ["Who is affected?", "What deadline matters?", "What changed?", "What should I monitor?"];
  return (
    <section className="chat-card">
      <div className="section-header compact-header">
        <div>
          <p className="eyebrow">Grounded to selected update</p>
          <h2>Insight chat</h2>
        </div>
      </div>
      <div className="suggestions">
        {prompts.map((prompt) => <button key={prompt} onClick={() => setChatInput(prompt)}>{prompt}</button>)}
      </div>
      {chatLoading ? (
        <div className="chat-reply chat-loading" aria-live="polite">
          <Loader2 size={16} className="spin-icon" /> Analyzing the selected regulatory update…
        </div>
      ) : null}
      {!chatLoading && chatReply ? <div className="chat-reply" aria-live="polite">{chatReply}</div> : null}
      <div className="chat-input">
        <input
          value={chatInput}
          onChange={(event) => setChatInput(event.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); void onAsk(); } }}
          disabled={!event || chatLoading}
          placeholder="Ask about this regulatory update…"
          maxLength={4000}
        />
        <button onClick={() => void onAsk()} disabled={!event || chatLoading || !chatInput.trim()} title="Send">
          {chatLoading ? <Loader2 size={18} className="spin-icon" /> : <Send size={18} />}
        </button>
      </div>
    </section>
  );
}

function ExportButtons({ onExport }: { onExport: (format: "json" | "csv" | "markdown") => Promise<void> }) {
  return (
    <div className="export-buttons" aria-label="Export latest news">
      <button onClick={() => void onExport("json")}><FileJson size={16} /> JSON</button>
      <button onClick={() => void onExport("csv")}><FileSpreadsheet size={16} /> CSV</button>
      <button onClick={() => void onExport("markdown")}><Download size={16} /> Markdown</button>
    </div>
  );
}

function MarkdownLite({ content }: { content: string }) {
  const elements: React.ReactNode[] = [];
  let listItems: React.ReactNode[] = [];
  const lines = content.split("\n");
  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(<ul key={`ul-${elements.length}`}>{listItems}</ul>);
      listItems = [];
    }
  };
  lines.forEach((line, index) => {
    if (line.startsWith("# ")) { flushList(); elements.push(<h1 key={index}>{line.slice(2)}</h1>); }
    else if (line.startsWith("## ")) { flushList(); elements.push(<h2 key={index}>{line.slice(3)}</h2>); }
    else if (line.startsWith("- ")) { listItems.push(<li key={index}>{line.slice(2)}</li>); }
    else if (!line.trim()) { flushList(); }
    else { flushList(); elements.push(<p key={index}>{line}</p>); }
  });
  flushList();
  return <div className="markdown-lite">{elements}</div>;
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <FileText size={24} aria-hidden />
      <h2>{title}</h2>
      <p>{body}</p>
    </div>
  );
}

function SkeletonList() {
  return (
    <div className="event-list">
      {[0, 1, 2].map((item) => <div key={item} className="skeleton-card" />)}
    </div>
  );
}

function FullPageStatus({ title, body }: { title: string; body: string }) {
  return (
    <main className="auth-screen">
      <section className="auth-card">
        <img src="/logo_mark.png" alt="" className="status-logo" />
        <h1>{title}</h1>
        <p className="muted">{body}</p>
      </section>
    </main>
  );
}

function routeTitle(route: RouteKey) {
  const titles: Record<RouteKey, string> = {
    today: "Today briefing",
    browse: "Browse archive",
    saved: "Saved updates",
    event: "Event detail",
    notifications: "Notifications",
    account: "Account",
    "admin-sources": "Source health",
    "admin-runs": "Pipeline runs",
    "api-docs": "Backend API docs",
    flow: "Complete flow",
  };
  return titles[route];
}
