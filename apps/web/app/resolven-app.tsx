"use client";

import type { Session } from "@supabase/supabase-js";
import {
  Activity,
  AlertCircle,
  ArrowRight,
  BarChart3,
  Bell,
  Bookmark,
  BookOpenText,
  CalendarClock,
  CheckCircle2,
  ClipboardCheck,
  Clock3,
  Database,
  Download,
  ExternalLink,
  FileSearch,
  FileText,
  Gauge,
  History,
  Layers3,
  LayoutDashboard,
  ListChecks,
  Loader2,
  LogOut,
  MessageSquareText,
  Network,
  Play,
  RefreshCw,
  Search,
  Send,
  Settings,
  ShieldCheck,
  Sparkles,
  Star,
  Target,
  UserCircle,
  Users,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import type {
  AdminAnalytics,
  AdminDocument,
  AdminEvent,
  AdminFamily,
  ChatHistoryItem,
  CrawlRun,
  DigestEvent,
  IntelligenceDeadline,
  IntelligenceReadiness,
  SourceHealth,
  SourcePage,
  SourcePageCheckpoint,
  StakeholderIntelligence,
  StakeholderObligationGroup,
  SubscriptionSettings,
} from "@/lib/api";
import {
  crawlSource,
  crawlSourcePage,
  downloadLatestExport,
  getAdminAnalytics,
  getAdminDocuments,
  getAdminEvents,
  getAdminFamilies,
  getChatHistory,
  getEvent,
  getEvents,
  getHealth,
  getIntelligenceDeadlines,
  getIntelligenceObligations,
  getIntelligenceReadiness,
  getLatestDigest,
  getRuns,
  getSourcePageCheckpoints,
  getSourcePages,
  getSources,
  getStakeholderIntelligence,
  getSubscriptions,
  markRead,
  saveSubscriptions,
  sendChat,
  toggleBookmark,
  toggleSource,
} from "@/lib/api";
import { supabase } from "@/lib/supabase";

type RouteKey =
  | "landing"
  | "dashboard"
  | "latest"
  | "today"
  | "browse"
  | "intelligence"
  | "deadlines"
  | "ask"
  | "saved"
  | "event"
  | "notifications"
  | "account"
  | "admin-dashboard"
  | "admin-sources"
  | "admin-pages"
  | "admin-runs"
  | "admin-events"
  | "admin-documents"
  | "admin-families"
  | "admin-checkpoints"
  | "admin-analytics"
  | "api-docs"
  | "flow";

type NormalizedRoute = Exclude<RouteKey, "today" | "browse">;

type NavItem = {
  href: string;
  label: string;
  route: NormalizedRoute;
  Icon: LucideIcon;
};

type ChatMessage = {
  role: "user" | "assistant";
  content: string;
  created_at?: string | null;
};

const defaultSettings: SubscriptionSettings = {
  jurisdictions: ["central"],
  source_ids: [],
  topics: ["solar", "tariff", "open access", "RPO/REC", "storage", "transmission"],
  email_enabled: true,
  frequency: "daily",
};

const userNav: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", route: "dashboard", Icon: LayoutDashboard },
  { href: "/latest", label: "Latest Updates", route: "latest", Icon: FileSearch },
  { href: "/intelligence", label: "Intelligence", route: "intelligence", Icon: Network },
  { href: "/deadlines", label: "Deadlines", route: "deadlines", Icon: CalendarClock },
  { href: "/ask", label: "Ask AI", route: "ask", Icon: MessageSquareText },
  { href: "/saved", label: "Saved", route: "saved", Icon: Star },
  { href: "/notifications", label: "Notifications", route: "notifications", Icon: Bell },
  { href: "/account", label: "Account", route: "account", Icon: UserCircle },
];

const adminNav: NavItem[] = [
  { href: "/admin", label: "Dashboard", route: "admin-dashboard", Icon: Gauge },
  { href: "/admin/sources", label: "Sources", route: "admin-sources", Icon: Database },
  { href: "/admin/pages", label: "Source Pages", route: "admin-pages", Icon: Layers3 },
  { href: "/admin/runs", label: "Crawl Runs", route: "admin-runs", Icon: History },
  { href: "/admin/events", label: "Events", route: "admin-events", Icon: ClipboardCheck },
  { href: "/admin/documents", label: "Documents", route: "admin-documents", Icon: FileText },
  { href: "/admin/families", label: "Families", route: "admin-families", Icon: Network },
  { href: "/admin/checkpoints", label: "Checkpoints", route: "admin-checkpoints", Icon: CheckCircle2 },
  { href: "/admin/analytics", label: "Analytics", route: "admin-analytics", Icon: BarChart3 },
];

const sourceOptions = ["all", "MNRE", "CERC", "SECI", "MoP", "MERC"];
const stakeholderOptions = [
  "all",
  "Solar Developers",
  "Wind Developers",
  "DISCOMs",
  "Transmission Licensees",
  "Power Exchanges",
  "Generators",
];
const eventTypeOptions = ["all", "NEW", "CHANGED", "REPLACEMENT", "DUPLICATE"];
const deadlineTypes = [
  "all",
  "CONSULTATION_DEADLINE",
  "TENDER_SUBMISSION_DEADLINE",
  "HEARING_DATE",
  "COMPLIANCE_DEADLINE",
  "IMPLEMENTATION_DATE",
  "PUBLICATION_DATE",
  "UNKNOWN_DATE",
];
const suggestedPrompts = [
  "What changed this week?",
  "Which regulations affect solar developers?",
  "What consultations close this month?",
  "What deadlines should I care about?",
];

function normalizeRoute(route: RouteKey): NormalizedRoute {
  if (route === "today") return "dashboard";
  if (route === "browse") return "latest";
  return route;
}

function formatDate(value?: string | null) {
  if (!value) return "Not specified";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  }).format(date);
}

function formatRelativeDate(value?: string | null) {
  if (!value) return "No recent run";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

function compactNumber(value?: number | null) {
  return new Intl.NumberFormat("en-IN").format(value ?? 0);
}

function deadlineLabel(event: DigestEvent) {
  const dates = event.summary?.important_dates ?? [];
  return dates[0] ?? null;
}

function eventStakeholders(event: DigestEvent) {
  return event.summary?.affected_segments?.filter(Boolean) ?? [];
}

function eventSummary(event: DigestEvent) {
  return (
    event.summary?.plain_english_summary ||
    event.raw_summary ||
    "Regulatory update detected from the source document. Review the source for full details."
  );
}

function isConsultation(event: DigestEvent) {
  const haystack = `${event.title} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
  return haystack.includes("comment") || haystack.includes("consultation") || haystack.includes("draft");
}

function isHighImpact(event: DigestEvent) {
  return (
    event.event_type === "CHANGED" ||
    event.summary?.action_required === "urgent" ||
    (event.summary?.confidence === "high" && eventStakeholders(event).length > 0)
  );
}

function stripMarkdownNoise(line: string) {
  return line.replace(/^#{1,6}\s*/, "").replace(/^\*\s*/, "").replace(/\*\*/g, "").trim();
}

function MarkdownLite({ content }: { content: string }) {
  if (!content.trim()) {
    return <p className="muted">Ask a question to generate an analyst-style answer.</p>;
  }
  const lines = content.split(/\r?\n/).filter((line) => line.trim());
  return (
    <div className="markdown-lite">
      {lines.map((line, index) => {
        const clean = stripMarkdownNoise(line);
        if (/^\|/.test(line)) {
          return (
            <code key={`${line}-${index}`} className="markdown-code">
              {clean.replace(/\|/g, "  ")}
            </code>
          );
        }
        if (/^[-*]\s+/.test(line) || /^\d+\.\s+/.test(line)) {
          return <p key={`${line}-${index}`} className="markdown-bullet">{clean}</p>;
        }
        if (/^#{1,6}\s+/.test(line)) {
          return <strong key={`${line}-${index}`}>{clean}</strong>;
        }
        return <p key={`${line}-${index}`}>{clean}</p>;
      })}
    </div>
  );
}

export function ResolvenApp({
  initialRoute,
  initialEventId,
}: {
  initialRoute: RouteKey;
  initialEventId?: number;
}) {
  const route = normalizeRoute(initialRoute);
  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const [digestDate, setDigestDate] = useState("");
  const [events, setEvents] = useState<DigestEvent[]>([]);
  const [selectedEvent, setSelectedEvent] = useState<DigestEvent | null>(null);
  const [sources, setSources] = useState<SourceHealth[]>([]);
  const [runs, setRuns] = useState<CrawlRun[]>([]);
  const [settings, setSettings] = useState<SubscriptionSettings>(defaultSettings);
  const [isAdmin, setIsAdmin] = useState(false);
  const [pipelineStatus, setPipelineStatus] = useState<"online" | "degraded" | "offline">("offline");

  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [stakeholderFilter, setStakeholderFilter] = useState("all");
  const [eventTypeFilter, setEventTypeFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("all");

  const [deadlines, setDeadlines] = useState<IntelligenceDeadline[]>([]);
  const [obligationGroups, setObligationGroups] = useState<StakeholderObligationGroup[]>([]);
  const [stakeholderViews, setStakeholderViews] = useState<StakeholderIntelligence[]>([]);
  const [readiness, setReadiness] = useState<IntelligenceReadiness | null>(null);
  const [intelligenceTab, setIntelligenceTab] = useState<"deadlines" | "obligations" | "stakeholders" | "readiness">("deadlines");
  const [deadlineType, setDeadlineType] = useState("all");
  const [deadlineStakeholder, setDeadlineStakeholder] = useState("all");

  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  const [sourcePages, setSourcePages] = useState<SourcePage[]>([]);
  const [checkpoints, setCheckpoints] = useState<SourcePageCheckpoint[]>([]);
  const [adminDocs, setAdminDocs] = useState<AdminDocument[]>([]);
  const [adminEvents, setAdminEvents] = useState<AdminEvent[]>([]);
  const [families, setFamilies] = useState<AdminFamily[]>([]);
  const [analytics, setAnalytics] = useState<AdminAnalytics | null>(null);

  const token = session?.access_token;
  const canRead = Boolean(token || demoMode);
  const userEmail = session?.user.email ?? (demoMode ? "local-preview@resolven.ai" : "");
  const sourceByCode = useMemo(
    () => new Map(sources.map((source) => [source.code.toLowerCase(), source])),
    [sources],
  );

  const filteredEvents = useMemo(() => {
    const today = new Date();
    return events.filter((event) => {
      const text = `${event.title} ${event.issuing_body ?? ""} ${event.topic_tags.join(" ")} ${eventSummary(event)}`.toLowerCase();
      if (query && !text.includes(query.toLowerCase())) return false;
      if (sourceFilter !== "all") {
        const sourceText = `${event.issuing_body ?? ""} ${event.source_url}`.toLowerCase();
        if (!sourceText.includes(sourceFilter.toLowerCase())) return false;
      }
      if (stakeholderFilter !== "all") {
        const stakeholders = eventStakeholders(event).join(" ").toLowerCase();
        if (!stakeholders.includes(stakeholderFilter.toLowerCase())) return false;
      }
      if (eventTypeFilter !== "all" && event.event_type !== eventTypeFilter) return false;
      if (dateFilter !== "all" && event.issue_date) {
        const eventDate = new Date(event.issue_date);
        const diffDays = Math.floor((today.getTime() - eventDate.getTime()) / 86_400_000);
        if (dateFilter === "week" && diffDays > 7) return false;
        if (dateFilter === "month" && diffDays > 31) return false;
      }
      return true;
    });
  }, [dateFilter, eventTypeFilter, events, query, sourceFilter, stakeholderFilter]);

  const savedEvents = useMemo(() => events.filter((event) => event.is_bookmarked), [events]);
  const activeDeadlines = useMemo(
    () =>
      deadlines.filter((deadline) => {
        if (deadline.days_remaining !== null && deadline.days_remaining < 0) return false;
        if (deadlineType !== "all" && deadline.deadline_type !== deadlineType) return false;
        if (deadlineStakeholder !== "all") {
          return deadline.stakeholders_affected.some((item) =>
            item.toLowerCase().includes(deadlineStakeholder.toLowerCase()),
          );
        }
        return true;
      }),
    [deadlineStakeholder, deadlineType, deadlines],
  );

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
    setSourceFilter(params.get("source") ?? "all");
  }, []);

  useEffect(() => {
    if (!authReady) return;
    if (!canRead) {
      setLoading(false);
      return;
    }
    void loadBaseData();
  }, [authReady, canRead]);

  useEffect(() => {
    if (!canRead) return;
    if (route === "event" && initialEventId) {
      void loadEvent(initialEventId);
    }
    if (route === "intelligence" || route === "deadlines" || route === "dashboard") {
      void loadIntelligenceData();
    }
    if (route === "ask") {
      void loadChatHistory();
    }
  }, [canRead, route, initialEventId]);

  useEffect(() => {
    if (!canRead || !isAdmin) return;
    if (route.startsWith("admin")) {
      void loadAdminData();
    }
  }, [canRead, isAdmin, route]);

  async function loadBaseData() {
    setLoading(true);
    setStatusMessage("");
    try {
      const [healthResult, digestResult, subscriptionResult] = await Promise.allSettled([
        getHealth(),
        getLatestDigest(token),
        getSubscriptions(token),
      ]);
      if (healthResult.status === "fulfilled") {
        setPipelineStatus(healthResult.value.status === "ok" ? "online" : "degraded");
      }
      if (digestResult.status === "fulfilled") {
        setDigestDate(digestResult.value.digest_date);
        setEvents(digestResult.value.events);
      }
      if (subscriptionResult.status === "fulfilled") {
        setSettings(subscriptionResult.value);
      }
      try {
        const [sourceRows, runRows] = await Promise.all([getSources(token), getRuns(token)]);
        setSources(sourceRows);
        setRuns(runRows);
        setIsAdmin(true);
      } catch {
        setIsAdmin(false);
      }
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to load workspace data.");
    } finally {
      setLoading(false);
    }
  }

  async function loadEvent(eventId: number) {
    try {
      const event = await getEvent(eventId, token);
      setSelectedEvent(event);
      await markRead(eventId, token).catch(() => undefined);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Event could not be loaded.");
    }
  }

  async function loadIntelligenceData() {
    try {
      const [deadlineRows, obligationRows, stakeholderRows, readinessRows] = await Promise.all([
        getIntelligenceDeadlines(token, { status: "active" }),
        getIntelligenceObligations(token),
        getStakeholderIntelligence(token),
        getIntelligenceReadiness(token),
      ]);
      setDeadlines(deadlineRows);
      setObligationGroups(obligationRows);
      setStakeholderViews(stakeholderRows);
      setReadiness(readinessRows);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Intelligence data is not available.");
    }
  }

  async function loadChatHistory() {
    try {
      const history = await getChatHistory(token);
      setChatMessages(
        history.map((item: ChatHistoryItem) => ({
          role: item.role,
          content: item.content,
          created_at: item.created_at,
        })),
      );
    } catch {
      setChatMessages([]);
    }
  }

  async function loadAdminData() {
    try {
      const [pageRows, checkpointRows, documentRows, eventRows, familyRows, analyticsRows] =
        await Promise.all([
          getSourcePages(token),
          getSourcePageCheckpoints(token),
          getAdminDocuments(token),
          getAdminEvents(token),
          getAdminFamilies(token),
          getAdminAnalytics(token),
        ]);
      setSourcePages(pageRows);
      setCheckpoints(checkpointRows);
      setAdminDocs(documentRows);
      setAdminEvents(eventRows);
      setFamilies(familyRows);
      setAnalytics(analyticsRows);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Admin data is not available.");
    }
  }

  async function handleSignIn() {
    setAuthMessage("");
    if (!supabase) {
      setDemoMode(true);
      return;
    }
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    if (error) setAuthMessage(error.message);
  }

  async function handleMagicLink() {
    setAuthMessage("");
    if (!supabase) {
      setDemoMode(true);
      return;
    }
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    setAuthMessage(error ? error.message : "Magic link sent. Check your inbox.");
  }

  async function handleSignOut() {
    if (supabase) await supabase.auth.signOut();
    setDemoMode(false);
    setSession(null);
  }

  async function handleSaveSettings() {
    setBusyAction("settings");
    try {
      const saved = await saveSubscriptions(settings, token);
      setSettings(saved);
      setStatusMessage("Notification preferences saved.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to save preferences.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleBookmark(event: DigestEvent) {
    setBusyAction(`bookmark-${event.id}`);
    try {
      const result = await toggleBookmark(event.id, token);
      setEvents((items) =>
        items.map((item) =>
          item.id === event.id ? { ...item, is_bookmarked: result.is_bookmarked } : item,
        ),
      );
      if (selectedEvent?.id === event.id) {
        setSelectedEvent({ ...selectedEvent, is_bookmarked: result.is_bookmarked });
      }
    } finally {
      setBusyAction(null);
    }
  }

  async function handleAsk(prompt?: string) {
    const message = (prompt ?? chatInput).trim();
    if (!message) return;
    setChatInput("");
    setChatLoading(true);
    const nextMessages: ChatMessage[] = [...chatMessages, { role: "user", content: message }];
    setChatMessages(nextMessages);
    try {
      const response = await sendChat(message, selectedEvent?.id ?? null, token);
      setChatMessages([...nextMessages, { role: "assistant", content: response.reply }]);
    } catch (error) {
      setChatMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: error instanceof Error ? error.message : "The assistant could not answer right now.",
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  async function handleToggleSource(source: SourceHealth) {
    setBusyAction(`source-${source.id}`);
    try {
      const updated = await toggleSource(source, token);
      setSources((rows) => rows.map((row) => (row.id === updated.id ? updated : row)));
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to update source.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handleSourceCrawl(source: SourceHealth) {
    setBusyAction(`crawl-source-${source.id}`);
    try {
      const result = await crawlSource(source.id, token);
      setStatusMessage(`Crawl finished: ${result.docs_found} documents, ${result.new_events} events.`);
      await loadBaseData();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to start source crawl.");
    } finally {
      setBusyAction(null);
    }
  }

  async function handlePageCrawl(page: SourcePage) {
    setBusyAction(`crawl-page-${page.id}`);
    try {
      const result = await crawlSourcePage(page.id, token);
      setStatusMessage(`Page crawl finished: ${result.docs_found} documents, ${result.new_events} events.`);
      await loadBaseData();
      await loadAdminData();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Unable to start page crawl.");
    } finally {
      setBusyAction(null);
    }
  }

  if (route === "landing") {
    return (
      <LandingPage
        canRead={canRead}
        email={email}
        password={password}
        authMessage={authMessage}
        onEmail={setEmail}
        onPassword={setPassword}
        onSignIn={handleSignIn}
        onMagicLink={handleMagicLink}
        onDemo={() => setDemoMode(true)}
      />
    );
  }

  if (!authReady || loading) {
    return (
      <div className="center-screen">
        <Loader2 className="spin" size={28} />
        <p>Loading Resolven Regulatory AI...</p>
      </div>
    );
  }

  if (!canRead) {
    return (
      <AuthScreen
        email={email}
        password={password}
        message={authMessage}
        onEmail={setEmail}
        onPassword={setPassword}
        onSignIn={handleSignIn}
        onMagicLink={handleMagicLink}
        onDemo={() => setDemoMode(true)}
      />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar
        route={route}
        isAdmin={isAdmin || demoMode}
        userEmail={userEmail}
        onSignOut={handleSignOut}
      />
      <main className="main-shell">
        <TopBar
          route={route}
          digestDate={digestDate}
          pipelineStatus={pipelineStatus}
          eventCount={events.length}
          isAdmin={isAdmin || demoMode}
        />
        {statusMessage ? (
          <div className="status-banner">
            <AlertCircle size={18} />
            <span>{statusMessage}</span>
            <button type="button" onClick={() => setStatusMessage("")}>
              Dismiss
            </button>
          </div>
        ) : null}
        {renderRoute()}
      </main>
    </div>
  );

  function renderRoute() {
    switch (route) {
      case "dashboard":
        return renderDashboard();
      case "latest":
        return renderLatest();
      case "intelligence":
        return renderIntelligence();
      case "deadlines":
        return renderDeadlines();
      case "ask":
        return renderAsk();
      case "saved":
        return renderSaved();
      case "event":
        return renderEventDetail();
      case "notifications":
        return renderNotifications();
      case "account":
        return renderAccount();
      case "admin-dashboard":
        return renderAdminDashboard();
      case "admin-sources":
        return renderAdminSources();
      case "admin-pages":
        return renderAdminPages();
      case "admin-runs":
        return renderAdminRuns();
      case "admin-events":
        return renderAdminEvents();
      case "admin-documents":
        return renderAdminDocuments();
      case "admin-families":
        return renderAdminFamilies();
      case "admin-checkpoints":
        return renderAdminCheckpoints();
      case "admin-analytics":
        return renderAdminAnalytics();
      case "api-docs":
        return renderDocs();
      case "flow":
        return renderFlow();
      default:
        return renderDashboard();
    }
  }

  function renderDashboard() {
    const consultations = events.filter(isConsultation).length;
    const highImpact = events.filter(isHighImpact).length;
    return (
      <div className="page-stack">
        <section className="metric-grid">
          <MetricCard title="New Updates Today" value={events.length} Icon={FileSearch} tone="purple" />
          <MetricCard title="Active Deadlines" value={activeDeadlines.length} Icon={CalendarClock} tone="green" />
          <MetricCard title="Consultations" value={consultations} Icon={MessageSquareText} tone="amber" />
          <MetricCard title="High Impact Changes" value={highImpact} Icon={AlertCircle} tone="red" />
        </section>
        <section className="two-column">
          <Panel
            title="Recent Intelligence Feed"
            icon={Sparkles}
            action={
              <a className="ghost-button" href="/latest">
                View all <ArrowRight size={16} />
              </a>
            }
          >
            <div className="event-list compact-list">
              {events.slice(0, 5).map((event) => (
                <EventCard
                  key={event.id}
                  event={event}
                  compact
                  onBookmark={() => void handleBookmark(event)}
                  busy={busyAction === `bookmark-${event.id}`}
                />
              ))}
              {!events.length ? <EmptyState title="No intelligence yet" body="Run curated sources to populate the intelligence feed." /> : null}
            </div>
          </Panel>
          <Panel title="Source Health" icon={ShieldCheck}>
            <div className="source-health-list">
              {sources.slice(0, 6).map((source) => (
                <div className="source-health-row" key={source.id}>
                  <span className={source.enabled ? "health-dot online" : "health-dot muted-dot"} />
                  <div>
                    <strong>{source.name}</strong>
                    <p>{source.last_status ?? "no status"} · {formatRelativeDate(source.last_checked_at)}</p>
                  </div>
                  <span className="mini-badge">{source.consecutive_failures} failures</span>
                </div>
              ))}
              {!sources.length ? <EmptyState title="No source health loaded" body="Admin source access is required for this panel." /> : null}
            </div>
          </Panel>
        </section>
      </div>
    );
  }

  function renderLatest() {
    return (
      <div className="page-stack">
        <section className="toolbar-panel">
          <div className="search-box">
            <Search size={18} />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search regulations, source, stakeholder, topic"
            />
          </div>
          <Select label="Source" value={sourceFilter} onChange={setSourceFilter} options={sourceOptions} />
          <Select label="Stakeholder" value={stakeholderFilter} onChange={setStakeholderFilter} options={stakeholderOptions} />
          <Select label="Event Type" value={eventTypeFilter} onChange={setEventTypeFilter} options={eventTypeOptions} />
          <Select label="Date" value={dateFilter} onChange={setDateFilter} options={["all", "week", "month"]} />
          <div className="export-group">
            <button type="button" onClick={() => void downloadLatestExport("csv", token)}>
              <Download size={16} /> CSV
            </button>
            <button type="button" onClick={() => void downloadLatestExport("markdown", token)}>
              <Download size={16} /> Markdown
            </button>
            <button type="button" onClick={() => void downloadLatestExport("json", token)}>
              <Download size={16} /> JSON
            </button>
          </div>
        </section>
        <section className="event-list">
          {filteredEvents.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              onBookmark={() => void handleBookmark(event)}
              busy={busyAction === `bookmark-${event.id}`}
            />
          ))}
          {!filteredEvents.length ? <EmptyState title="No matching updates" body="Try removing filters or run the curated crawl." /> : null}
        </section>
      </div>
    );
  }

  function renderIntelligence() {
    return (
      <div className="page-stack">
        <div className="tab-row">
          {[
            ["deadlines", "Deadlines"],
            ["obligations", "Obligations"],
            ["stakeholders", "Stakeholders"],
            ["readiness", "Readiness"],
          ].map(([key, label]) => (
            <button
              key={key}
              type="button"
              className={intelligenceTab === key ? "active" : ""}
              onClick={() => setIntelligenceTab(key as typeof intelligenceTab)}
            >
              {label}
            </button>
          ))}
        </div>
        {intelligenceTab === "deadlines" ? renderDeadlines(true) : null}
        {intelligenceTab === "obligations" ? (
          <Panel title="Stakeholder Obligations" icon={ListChecks}>
            <div className="stack-list">
              {obligationGroups.map((group) => (
                <div className="intelligence-row" key={group.stakeholder}>
                  <h3>{group.stakeholder}</h3>
                  {group.obligations.slice(0, 5).map((item, index) => (
                    <p key={`${group.stakeholder}-${index}`}>
                      {item.obligation} <span>{item.deadline_date ? `Due ${formatDate(item.deadline_date)}` : "No deadline found"}</span>
                    </p>
                  ))}
                </div>
              ))}
              {!obligationGroups.length ? <EmptyState title="No obligations extracted" body="Graph extraction has not produced obligation rows yet." /> : null}
            </div>
          </Panel>
        ) : null}
        {intelligenceTab === "stakeholders" ? (
          <section className="stakeholder-grid">
            {stakeholderViews.map((view) => (
              <Panel key={view.stakeholder} title={view.stakeholder} icon={Users}>
                <p className="lead-copy">{view.impact_summary}</p>
                <div className="mini-grid">
                  <span>{view.counts.regulations ?? 0} regulations</span>
                  <span>{view.counts.obligations ?? 0} obligations</span>
                  <span>{view.counts.deadlines ?? 0} deadlines</span>
                  <span>{view.counts.tenders ?? 0} tenders</span>
                </div>
                <p>{view.action_summary}</p>
              </Panel>
            ))}
            {!stakeholderViews.length ? <EmptyState title="No stakeholder graph yet" body="Run accepted documents through graph extraction to populate this view." /> : null}
          </section>
        ) : null}
        {intelligenceTab === "readiness" ? (
          <Panel title="Regulatory Readiness" icon={Target}>
            <div className="readiness-grid">
              <MetricCard title="Active Deadlines" value={readiness?.active_deadlines.length ?? 0} Icon={CalendarClock} tone="green" />
              <MetricCard title="Obligation Groups" value={readiness?.stakeholder_obligations.length ?? 0} Icon={ListChecks} tone="purple" />
              <MetricCard title="Regulatory Impacts" value={readiness?.regulatory_impacts.length ?? 0} Icon={Network} tone="amber" />
            </div>
            {(readiness?.notes ?? []).map((note) => (
              <p className="note-line" key={note}>{note}</p>
            ))}
          </Panel>
        ) : null}
      </div>
    );
  }

  function renderDeadlines(embedded = false) {
    return (
      <div className={embedded ? "page-stack embedded" : "page-stack"}>
        {!embedded ? null : null}
        <section className="toolbar-panel">
          <Select label="Deadline Type" value={deadlineType} onChange={setDeadlineType} options={deadlineTypes} />
          <Select label="Stakeholder" value={deadlineStakeholder} onChange={setDeadlineStakeholder} options={stakeholderOptions} />
          <button type="button" onClick={() => void loadIntelligenceData()}>
            <RefreshCw size={16} /> Refresh
          </button>
        </section>
        <section className="deadline-list">
          {activeDeadlines.map((deadline) => (
            <div className="deadline-card" key={`${deadline.document_id}-${deadline.deadline_type}-${deadline.deadline_date}`}>
              <div className="deadline-days">
                <strong>{deadline.days_remaining ?? "--"}</strong>
                <span>days</span>
              </div>
              <div>
                <div className="row-wrap">
                  <span className="mini-badge">{deadline.issuer ?? "Unknown issuer"}</span>
                  <span className="mini-badge green">{deadline.deadline_type.replaceAll("_", " ")}</span>
                </div>
                <h3>{deadline.title}</h3>
                <p>{deadline.evidence ?? "Deadline detected from regulatory graph extraction."}</p>
                <div className="row-wrap">
                  <strong>{formatDate(deadline.deadline_date)}</strong>
                  {deadline.stakeholders_affected.map((item) => <span className="tag" key={item}>{item}</span>)}
                </div>
              </div>
              <a className="icon-link" href={deadline.source_url} target="_blank" rel="noreferrer">
                <ExternalLink size={18} />
              </a>
            </div>
          ))}
          {!activeDeadlines.length ? <EmptyState title="No active deadlines" body="No future deadlines match the current filters." /> : null}
        </section>
      </div>
    );
  }

  function renderAsk() {
    return (
      <section className="ask-layout">
        <aside className="chat-history">
          <h2>History</h2>
          {chatMessages.slice(-12).map((message, index) => (
            <button key={`${message.role}-${index}`} type="button" onClick={() => setChatInput(message.content)}>
              <span>{message.role === "user" ? "Question" : "Answer"}</span>
              {stripMarkdownNoise(message.content).slice(0, 84)}
            </button>
          ))}
        </aside>
        <div className="chat-panel">
          <div className="suggestion-row">
            {suggestedPrompts.map((prompt) => (
              <button key={prompt} type="button" onClick={() => void handleAsk(prompt)}>
                {prompt}
              </button>
            ))}
          </div>
          <div className="message-stream">
            {chatMessages.map((message, index) => (
              <div key={`${message.role}-${index}`} className={`message ${message.role}`}>
                <MarkdownLite content={message.content} />
              </div>
            ))}
            {chatLoading ? (
              <div className="message assistant">
                <Loader2 className="spin" size={18} /> Thinking through the regulatory context...
              </div>
            ) : null}
          </div>
          <form
            className="ask-composer"
            onSubmit={(event) => {
              event.preventDefault();
              void handleAsk();
            }}
          >
            <input
              value={chatInput}
              onChange={(event) => setChatInput(event.target.value)}
              placeholder="Ask about deadlines, stakeholders, consultations, or policy impact"
            />
            <button type="submit" disabled={chatLoading}>
              {chatLoading ? <Loader2 className="spin" size={18} /> : <Send size={18} />}
            </button>
          </form>
        </div>
      </section>
    );
  }

  function renderSaved() {
    return (
      <div className="page-stack">
        <section className="metric-grid three">
          <MetricCard title="Saved Events" value={savedEvents.length} Icon={Star} tone="purple" />
          <MetricCard title="Saved Deadlines" value={activeDeadlines.length} Icon={CalendarClock} tone="green" />
          <MetricCard title="Saved Consultations" value={savedEvents.filter(isConsultation).length} Icon={MessageSquareText} tone="amber" />
        </section>
        <section className="event-list">
          {savedEvents.map((event) => (
            <EventCard
              key={event.id}
              event={event}
              onBookmark={() => void handleBookmark(event)}
              busy={busyAction === `bookmark-${event.id}`}
            />
          ))}
          {!savedEvents.length ? <EmptyState title="No saved intelligence" body="Use the bookmark action on any update to save it here." /> : null}
        </section>
      </div>
    );
  }

  function renderEventDetail() {
    const event = selectedEvent;
    if (!event) {
      return <EmptyState title="Event not found" body="The selected regulatory event could not be loaded." />;
    }
    return (
      <section className="detail-layout">
        <div className="detail-main">
          <div className="detail-heading">
            <span className="mini-badge">{event.issuing_body ?? "Unknown source"}</span>
            <span className="mini-badge green">{event.event_type}</span>
            <span className="mini-badge">{formatDate(event.issue_date)}</span>
          </div>
          <h1>{event.title}</h1>
          <Panel title="What Changed" icon={FileSearch}>
            <p>{eventSummary(event)}</p>
          </Panel>
          <Panel title="Why It Matters" icon={Sparkles}>
            <p>{event.summary?.why_it_matters ?? "The intelligence layer has not produced an impact explanation for this event yet."}</p>
          </Panel>
          <Panel title="Action Required" icon={ClipboardCheck}>
            <p>{event.summary?.action_required ?? "monitor"}</p>
            <div className="row-wrap">
              {event.summary?.important_dates.map((date) => <span className="tag green" key={date}>{date}</span>)}
            </div>
          </Panel>
        </div>
        <aside className="detail-side">
          <a className="primary-button full" href={event.source_url} target="_blank" rel="noreferrer">
            Open Government Source <ExternalLink size={17} />
          </a>
          <button className="secondary-button full" type="button" onClick={() => void handleBookmark(event)}>
            <Bookmark size={17} /> {event.is_bookmarked ? "Saved" : "Save"}
          </button>
          <Panel title="Affected Stakeholders" icon={Users}>
            <div className="row-wrap">
              {eventStakeholders(event).map((item) => <span className="tag" key={item}>{item}</span>)}
              {!eventStakeholders(event).length ? <span className="muted">No stakeholder found</span> : null}
            </div>
          </Panel>
        </aside>
      </section>
    );
  }

  function renderNotifications() {
    return (
      <Panel title="Notification Preferences" icon={Bell}>
        <div className="settings-grid">
          <label>
            Sources
            <select
              value={settings.source_ids[0] ?? ""}
              onChange={(event) => setSettings({ ...settings, source_ids: event.target.value ? [Number(event.target.value)] : [] })}
            >
              <option value="">All sources</option>
              {sources.map((source) => <option key={source.id} value={source.id}>{source.name}</option>)}
            </select>
          </label>
          <label>
            Stakeholders and topics
            <input
              value={settings.topics.join(", ")}
              onChange={(event) =>
                setSettings({
                  ...settings,
                  topics: event.target.value.split(",").map((item) => item.trim()).filter(Boolean),
                })
              }
            />
          </label>
          <label>
            Email frequency
            <select
              value={settings.frequency}
              onChange={(event) => setSettings({ ...settings, frequency: event.target.value as "daily" | "instant" })}
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
          <button className="primary-button" type="button" onClick={() => void handleSaveSettings()} disabled={busyAction === "settings"}>
            {busyAction === "settings" ? <Loader2 className="spin" size={16} /> : <CheckCircle2 size={16} />} Save
          </button>
        </div>
      </Panel>
    );
  }

  function renderAccount() {
    return (
      <section className="two-column">
        <Panel title="Profile" icon={UserCircle}>
          <div className="profile-card">
            <img src="/logo_mark.png" alt="Resolven logo" />
            <div>
              <h3>{userEmail}</h3>
              <p>{demoMode ? "Local preview user" : "Authenticated user"}</p>
            </div>
          </div>
        </Panel>
        <Panel title="Subscription" icon={ShieldCheck}>
          <p className="lead-copy">Resolven Regulatory AI workspace access is active.</p>
          <p>Role: {isAdmin || demoMode ? "Admin" : "User"}</p>
        </Panel>
      </section>
    );
  }

  function renderAdminDashboard() {
    return (
      <div className="page-stack">
        <section className="metric-grid">
          <MetricCard title="Sources" value={analytics?.sources ?? sources.length} Icon={Database} tone="purple" />
          <MetricCard title="Pages" value={analytics?.pages ?? sourcePages.length} Icon={Layers3} tone="green" />
          <MetricCard title="Events" value={analytics?.events ?? events.length} Icon={ClipboardCheck} tone="amber" />
          <MetricCard title="Acceptance Rate" value={`${analytics?.acceptance_rate ?? 0}%`} Icon={Gauge} tone="red" />
        </section>
        <section className="two-column">
          <Panel title="Checkpoint Savings" icon={CheckCircle2}>
            <div className="big-stat">{analytics?.runtime_reduction ?? 96}%</div>
            <p>Runtime reduction from incremental crawl checkpoints.</p>
            <p>{analytics?.download_reduction ?? 96}% download reduction.</p>
          </Panel>
          <Panel title="Latest Crawl Runs" icon={History}>
            <AdminRows
              rows={runs.slice(0, 6)}
              columns={[
                ["Run", (row) => `#${row.id}`],
                ["Status", (row) => row.status],
                ["Docs", (row) => compactNumber(row.docs_found)],
                ["Events", (row) => compactNumber(row.new_events)],
              ]}
            />
          </Panel>
        </section>
      </div>
    );
  }

  function renderAdminSources() {
    return (
      <Panel title="Sources" icon={Database} action={<button type="button" onClick={() => void loadBaseData()}><RefreshCw size={16} /> Refresh</button>}>
        <AdminRows
          rows={sources}
          columns={[
            ["Code", (row) => row.code],
            ["Name", (row) => row.name],
            ["Status", (row) => (row.enabled ? "Enabled" : "Disabled")],
            ["Failures", (row) => compactNumber(row.consecutive_failures)],
            [
              "Actions",
              (row) => (
                <div className="row-actions">
                  <button type="button" onClick={() => void handleToggleSource(row)} disabled={busyAction === `source-${row.id}`}>
                    {busyAction === `source-${row.id}` ? <Loader2 className="spin" size={15} /> : <Settings size={15} />}
                    {row.enabled ? "Disable" : "Enable"}
                  </button>
                  <button type="button" onClick={() => void handleSourceCrawl(row)} disabled={busyAction === `crawl-source-${row.id}`}>
                    {busyAction === `crawl-source-${row.id}` ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
                    Crawl
                  </button>
                </div>
              ),
            ],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminPages() {
    return (
      <Panel title="Source Pages" icon={Layers3}>
        <AdminRows
          rows={sourcePages}
          columns={[
            ["Source", (row) => row.source_code],
            ["Page", (row) => row.name],
            ["Type", (row) => row.page_type],
            ["Priority", (row) => row.priority],
            ["Last Crawled", (row) => formatRelativeDate(row.last_crawled_at)],
            [
              "Action",
              (row) => (
                <button type="button" onClick={() => void handlePageCrawl(row)} disabled={busyAction === `crawl-page-${row.id}`}>
                  {busyAction === `crawl-page-${row.id}` ? <Loader2 className="spin" size={15} /> : <Play size={15} />}
                  Crawl
                </button>
              ),
            ],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminRuns() {
    return (
      <Panel title="Crawl Runs" icon={History}>
        <AdminRows
          rows={runs}
          columns={[
            ["Run", (row) => `#${row.id}`],
            ["Started", (row) => formatRelativeDate(row.started_at)],
            ["Status", (row) => row.status],
            ["Sources", (row) => `${row.sources_succeeded}/${row.sources_attempted}`],
            ["Docs", (row) => compactNumber(row.docs_found)],
            ["Events", (row) => compactNumber(row.new_events)],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminEvents() {
    return (
      <Panel title="Events" icon={ClipboardCheck}>
        <AdminRows
          rows={adminEvents}
          columns={[
            ["ID", (row) => `#${row.id}`],
            ["Source", (row) => row.source_code ?? "unknown"],
            ["Title", (row) => <span className="table-title">{row.title}</span>],
            ["Quality", (row) => row.quality_score ?? "n/a"],
            ["Significance", (row) => row.significance_score ?? "n/a"],
            ["Status", (row) => (row.suppressed ? "Suppressed" : "Visible")],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminDocuments() {
    return (
      <Panel title="Documents" icon={FileText}>
        <AdminRows
          rows={adminDocs}
          columns={[
            ["ID", (row) => `#${row.id}`],
            ["Source", (row) => row.source_code ?? "unknown"],
            ["Title", (row) => <span className="table-title">{row.title}</span>],
            ["Type", (row) => row.doc_type ?? "unknown"],
            ["Family", (row) => row.family_title ?? "unassigned"],
            ["Seen", (row) => formatRelativeDate(row.last_seen_at)],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminFamilies() {
    return (
      <Panel title="Document Families" icon={Network}>
        <AdminRows
          rows={families}
          columns={[
            ["Family", (row) => <span className="table-title">{row.canonical_title}</span>],
            ["Issuer", (row) => row.issuer ?? "unknown"],
            ["Docs", (row) => compactNumber(row.document_count)],
            ["Versions", (row) => compactNumber(row.version_count)],
            ["Deadlines", (row) => compactNumber(row.deadline_count)],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminCheckpoints() {
    return (
      <Panel title="Incremental Crawl Checkpoints" icon={CheckCircle2}>
        <AdminRows
          rows={checkpoints}
          columns={[
            ["Source", (row) => row.source_code],
            ["Page", (row) => row.source_page],
            ["Checkpoint", (row) => <span className="table-title">{row.checkpoint_title ?? "not set"}</span>],
            ["Lookback", (row) => row.lookback_count ?? 3],
            ["Updated", (row) => formatRelativeDate(row.updated_at)],
          ]}
        />
      </Panel>
    );
  }

  function renderAdminAnalytics() {
    return (
      <div className="page-stack">
        <section className="metric-grid">
          <MetricCard title="Candidates" value={analytics?.candidates ?? 0} Icon={FileSearch} tone="purple" />
          <MetricCard title="Accepted" value={analytics?.accepted_candidates ?? 0} Icon={CheckCircle2} tone="green" />
          <MetricCard title="Rejected" value={analytics?.rejected_candidates ?? 0} Icon={AlertCircle} tone="red" />
          <MetricCard title="Families" value={analytics?.families ?? 0} Icon={Network} tone="amber" />
        </section>
        <Panel title="Top Rejection Reasons" icon={Activity}>
          <div className="reason-list">
            {(analytics?.rejected_reasons ?? []).map((reason) => (
              <div key={reason.reason_code ?? "unknown"}>
                <span>{reason.reason_code ?? "unknown"}</span>
                <strong>{compactNumber(reason.count)}</strong>
              </div>
            ))}
          </div>
        </Panel>
      </div>
    );
  }

  function renderDocs() {
    return (
      <Panel title="API Documentation" icon={BookOpenText}>
        <p className="lead-copy">The app uses existing Resolven backend APIs for auth, events, intelligence, chat, admin sources, source pages, crawl runs, checkpoints, documents, families, exports, and analytics.</p>
        <div className="doc-grid">
          {[
            ["Auth", "/auth/profile, Supabase session"],
            ["Events", "/events, /events/{id}, /exports/latest"],
            ["Intelligence", "/intelligence/deadlines, /obligations, /stakeholders, /readiness"],
            ["Chat", "/chat, /chat/history"],
            ["Admin", "/admin/sources, /admin/pages, /admin/checkpoints, /admin/documents, /admin/events, /admin/families, /admin/analytics"],
          ].map(([title, text]) => (
            <div key={title}>
              <strong>{title}</strong>
              <p>{text}</p>
            </div>
          ))}
        </div>
      </Panel>
    );
  }

  function renderFlow() {
    return (
      <Panel title="Data Flow" icon={Network}>
        <div className="flow-steps">
          {[
            "Curated source page",
            "Source-specific parser",
            "Primary document acquisition",
            "Extraction and OCR",
            "Family and version registry",
            "Knowledge graph",
            "Intelligence gate",
            "User-facing event",
          ].map((step, index) => (
            <div key={step}>
              <span>{index + 1}</span>
              <strong>{step}</strong>
            </div>
          ))}
        </div>
      </Panel>
    );
  }
}

function LandingPage({
  canRead,
  email,
  password,
  authMessage,
  onEmail,
  onPassword,
  onSignIn,
  onMagicLink,
  onDemo,
}: {
  canRead: boolean;
  email: string;
  password: string;
  authMessage: string;
  onEmail: (value: string) => void;
  onPassword: (value: string) => void;
  onSignIn: () => void;
  onMagicLink: () => void;
  onDemo: () => void;
}) {
  return (
    <main className="landing-page">
      <nav className="landing-nav">
        <img src="/logo_wordmark.png" alt="Resolven" />
        <div>
          <a href="/dashboard">Sign In</a>
          <a className="primary-button" href="mailto:hello@resolven.ai">Request Demo</a>
        </div>
      </nav>
      <section className="landing-hero">
        <div>
          <span className="eyebrow">Resolven Regulatory AI</span>
          <h1>Monitor Regulatory Changes Before They Impact Your Business</h1>
          <p>
            Track Indian energy regulatory changes, understand why they matter, and see the
            deadlines, obligations, consultations, tenders, and stakeholders affected.
          </p>
          <div className="hero-actions">
            <a className="primary-button" href={canRead ? "/dashboard" : "#signin"}>
              Open Dashboard <ArrowRight size={18} />
            </a>
            <a className="secondary-button" href="mailto:hello@resolven.ai">
              Request Demo
            </a>
          </div>
        </div>
        <div className="landing-preview" id="signin">
          <img src="/logo_mark.png" alt="Resolven logo" />
          <h2>Sign in</h2>
          <input value={email} onChange={(event) => onEmail(event.target.value)} placeholder="Email" />
          <input
            value={password}
            onChange={(event) => onPassword(event.target.value)}
            placeholder="Password"
            type="password"
          />
          <button className="primary-button full" type="button" onClick={onSignIn}>
            Sign In
          </button>
          <button className="secondary-button full" type="button" onClick={onMagicLink}>
            Send Magic Link
          </button>
          <button className="ghost-button full" type="button" onClick={onDemo}>
            Continue Local Preview
          </button>
          {authMessage ? <p className="notice">{authMessage}</p> : null}
        </div>
      </section>
    </main>
  );
}

function AuthScreen(props: {
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
        <button className="primary-button full" type="button" onClick={props.onSignIn}>Sign In</button>
        <button className="secondary-button full" type="button" onClick={props.onMagicLink}>Send Magic Link</button>
        <button className="ghost-button full" type="button" onClick={props.onDemo}>Continue Local Preview</button>
        {props.message ? <p className="notice">{props.message}</p> : null}
      </div>
    </div>
  );
}

function Sidebar({
  route,
  isAdmin,
  userEmail,
  onSignOut,
}: {
  route: NormalizedRoute;
  isAdmin: boolean;
  userEmail: string;
  onSignOut: () => void;
}) {
  return (
    <aside className="sidebar">
      <a className="brand-block" href="/dashboard">
        <img src="/logo_mark.png" alt="Resolven logo" />
        <div>
          <strong>Resolven Regulatory AI</strong>
          <span>{userEmail}</span>
        </div>
      </a>
      <nav>
        <span className="nav-label">Workspace</span>
        {userNav.map((item) => (
          <a key={item.href} className={route === item.route ? "active" : ""} href={item.href}>
            <item.Icon size={18} />
            {item.label}
          </a>
        ))}
        {isAdmin ? (
          <>
            <span className="nav-label">Admin</span>
            {adminNav.map((item) => (
              <a key={item.href} className={route === item.route ? "active" : ""} href={item.href}>
                <item.Icon size={18} />
                {item.label}
              </a>
            ))}
            <a className={route === "api-docs" ? "active" : ""} href="/api-docs">
              <BookOpenText size={18} />
              API Docs
            </a>
            <a className={route === "flow" ? "active" : ""} href="/flow">
              <Network size={18} />
              Flow
            </a>
          </>
        ) : null}
      </nav>
      <button className="sign-out" type="button" onClick={onSignOut}>
        <LogOut size={18} />
        Sign out
      </button>
    </aside>
  );
}

function TopBar({
  route,
  digestDate,
  pipelineStatus,
  eventCount,
  isAdmin,
}: {
  route: NormalizedRoute;
  digestDate: string;
  pipelineStatus: "online" | "degraded" | "offline";
  eventCount: number;
  isAdmin: boolean;
}) {
  const titleMap: Record<NormalizedRoute, string> = {
    landing: "Resolven Regulatory AI",
    dashboard: "Regulatory Intelligence Dashboard",
    latest: "Latest Regulatory Updates",
    intelligence: "Intelligence Center",
    deadlines: "Deadlines Center",
    ask: "Ask AI",
    saved: "Saved Intelligence",
    event: "Regulatory Event",
    notifications: "Notifications",
    account: "Account",
    "admin-dashboard": "Admin Dashboard",
    "admin-sources": "Sources",
    "admin-pages": "Source Pages",
    "admin-runs": "Crawl Runs",
    "admin-events": "Events",
    "admin-documents": "Documents",
    "admin-families": "Document Families",
    "admin-checkpoints": "Checkpoints",
    "admin-analytics": "Analytics",
    "api-docs": "API Documentation",
    flow: "Data Flow",
  };
  return (
    <header className="topbar">
      <div>
        <span className="eyebrow">{isAdmin ? "Admin enabled" : "User workspace"}</span>
        <h1>{titleMap[route]}</h1>
        <p>{eventCount} updates · latest digest {formatDate(digestDate)}</p>
      </div>
      <div className="topbar-actions">
        <span className={`status-pill ${pipelineStatus}`}>
          <span />
          {pipelineStatus}
        </span>
        <a className="secondary-button" href="/landing">Landing</a>
      </div>
    </header>
  );
}

function MetricCard({
  title,
  value,
  Icon,
  tone,
}: {
  title: string;
  value: number | string;
  Icon: LucideIcon;
  tone: "purple" | "green" | "amber" | "red";
}) {
  return (
    <article className={`metric-card ${tone}`}>
      <div>
        <span>{title}</span>
        <strong>{typeof value === "number" ? compactNumber(value) : value}</strong>
      </div>
      <Icon size={22} />
    </article>
  );
}

function Panel({
  title,
  icon: Icon,
  action,
  children,
}: {
  title: string;
  icon: LucideIcon;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="panel">
      <div className="panel-header">
        <h2>
          <Icon size={19} />
          {title}
        </h2>
        {action}
      </div>
      {children}
    </section>
  );
}

function EventCard({
  event,
  compact = false,
  onBookmark,
  busy,
}: {
  event: DigestEvent;
  compact?: boolean;
  onBookmark: () => void;
  busy: boolean;
}) {
  const sourceCode =
    event.issuing_body?.split(/\s+/)[0]?.replace(/[^A-Za-z]/g, "") ||
    new URL(event.source_url, "https://example.com").hostname.split(".")[0].toUpperCase();
  return (
    <article className={`event-card ${compact ? "compact" : ""}`}>
      <div className="event-source">
        <span>{sourceCode.slice(0, 5)}</span>
        <div>
          <strong>{event.issuing_body ?? "Government source"}</strong>
          <p>{formatDate(event.issue_date)}</p>
        </div>
      </div>
      <div className="event-body">
        <div className="row-wrap">
          <span className="mini-badge green">{event.event_type}</span>
          {event.topic_tags.slice(0, 4).map((tag) => <span className="tag" key={tag}>{tag}</span>)}
        </div>
        <h3>{event.title}</h3>
        <p>{eventSummary(event)}</p>
        <div className="row-wrap">
          {deadlineLabel(event) ? <span className="deadline-chip"><Clock3 size={15} /> {deadlineLabel(event)}</span> : null}
          {eventStakeholders(event).slice(0, 4).map((stakeholder) => <span className="tag purple" key={stakeholder}>{stakeholder}</span>)}
        </div>
      </div>
      <div className="event-actions">
        <button type="button" onClick={onBookmark} disabled={busy} title="Save event">
          {busy ? <Loader2 className="spin" size={17} /> : <Bookmark size={17} />}
        </button>
        <a href={event.source_url} target="_blank" rel="noreferrer" title="Open source">
          <ExternalLink size={17} />
        </a>
        <a href={`/events/${event.id}`} title="Open event">
          <ArrowRight size={17} />
        </a>
      </div>
    </article>
  );
}

function Select({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
}) {
  return (
    <label className="select-field">
      <span>{label}</span>
      <select value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map((option) => (
          <option key={option} value={option}>
            {option === "all" ? "All" : option.replaceAll("_", " ")}
          </option>
        ))}
      </select>
    </label>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <Sparkles size={22} />
      <h3>{title}</h3>
      <p>{body}</p>
    </div>
  );
}

function AdminRows<T>({
  rows,
  columns,
}: {
  rows: T[];
  columns: Array<[string, (row: T) => React.ReactNode]>;
}) {
  if (!rows.length) {
    return <EmptyState title="No rows" body="No records are available for this admin view." />;
  }
  return (
    <div className="admin-table">
      <div className="admin-table-head" style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(120px, 1fr))` }}>
        {columns.map(([label]) => <strong key={label}>{label}</strong>)}
      </div>
      {rows.map((row, rowIndex) => (
        <div className="admin-table-row" key={rowIndex} style={{ gridTemplateColumns: `repeat(${columns.length}, minmax(120px, 1fr))` }}>
          {columns.map(([label, render]) => <div key={label}>{render(row)}</div>)}
        </div>
      ))}
    </div>
  );
}
