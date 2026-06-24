"use client";

import type { Session } from "@supabase/supabase-js";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import type {
  DigestEvent,
  DigestResponse,
  SourceHealth,
  SourcePage,
  SubscriptionSettings,
} from "@/lib/api";
import {
  crawlSource,
  crawlSourcePage,
  downloadLatestExport,
  markRead,
  saveSubscriptions,
  sendChat,
  toggleBookmark,
  toggleSource,
} from "@/lib/api";
import {
  queryKeys,
  useAdminAnalyticsQuery,
  useAdminDocumentsQuery,
  useAdminEventsQuery,
  useAdminFamiliesQuery,
  useChatHistoryQuery,
  useCheckpointsQuery,
  useDeadlinesQuery,
  useDigestQuery,
  useEventQuery,
  useHealthQuery,
  useObligationsQuery,
  useReadinessQuery,
  useRunsQuery,
  useSourcePagesQuery,
  useSourcesQuery,
  useStakeholdersQuery,
  useSubscriptionsQuery,
} from "@/lib/queries";
import { supabase } from "@/lib/supabase";

import { eventStakeholders, eventSummary } from "./format";
import { defaultSettings, normalizeRoute } from "./types";
import type {
  ChatMessage,
  IntelligenceTab,
  PipelineStatus,
  RouteKey,
} from "./types";

export type QueryStatus = {
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  isSuccess: boolean;
  error: unknown;
  refetch: () => void;
};

type QueryLike = {
  isLoading: boolean;
  isError: boolean;
  isFetching: boolean;
  isSuccess: boolean;
  error: unknown;
  refetch: () => unknown;
};

function statusFrom(query: QueryLike): QueryStatus {
  return {
    isLoading: query.isLoading,
    isError: query.isError,
    isFetching: query.isFetching,
    isSuccess: query.isSuccess,
    error: query.error,
    refetch: () => {
      void query.refetch();
    },
  };
}

function combineStatus(parts: QueryStatus[]): QueryStatus {
  return {
    isLoading: parts.some((part) => part.isLoading),
    isError: parts.some((part) => part.isError),
    isFetching: parts.some((part) => part.isFetching),
    isSuccess: parts.length > 0 && parts.every((part) => part.isSuccess),
    error: parts.find((part) => part.isError)?.error,
    refetch: () => parts.forEach((part) => part.refetch()),
  };
}

function errorMessage(error: unknown, fallback: string) {
  return error instanceof Error ? error.message : fallback;
}

function useWorkspaceController(initialRoute: RouteKey, initialEventId?: number) {
  const route = normalizeRoute(initialRoute);
  const queryClient = useQueryClient();

  const [session, setSession] = useState<Session | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const [demoMode, setDemoMode] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [statusMessage, setStatusMessage] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);

  const [settings, setSettings] = useState<SubscriptionSettings>(defaultSettings);

  const [query, setQuery] = useState("");
  const [sourceFilter, setSourceFilter] = useState("all");
  const [stakeholderFilter, setStakeholderFilter] = useState("all");
  const [eventTypeFilter, setEventTypeFilter] = useState("all");
  const [dateFilter, setDateFilter] = useState("all");

  const [intelligenceTab, setIntelligenceTab] = useState<IntelligenceTab>("deadlines");
  const [deadlineType, setDeadlineType] = useState("all");
  const [deadlineStakeholder, setDeadlineStakeholder] = useState("all");

  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);

  const token = session?.access_token;
  const canRead = Boolean(token || demoMode);

  /* ---------------- Auth ---------------- */
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

  /* ---------------- Server state (TanStack Query) ---------------- */
  const healthQuery = useHealthQuery();
  const digestQuery = useDigestQuery(token, canRead);
  const subscriptionsQuery = useSubscriptionsQuery(token, canRead);
  const sourcesQuery = useSourcesQuery(token, canRead);
  const runsQuery = useRunsQuery(token, canRead);

  const isAdmin = sourcesQuery.isSuccess && runsQuery.isSuccess;

  const intelligenceEnabled =
    canRead && (route === "intelligence" || route === "deadlines" || route === "dashboard");
  const deadlinesQuery = useDeadlinesQuery(token, intelligenceEnabled);
  const obligationsQuery = useObligationsQuery(token, intelligenceEnabled);
  const stakeholdersQuery = useStakeholdersQuery(token, intelligenceEnabled);
  const readinessQuery = useReadinessQuery(token, intelligenceEnabled);

  const eventQuery = useEventQuery(initialEventId, token, canRead && route === "event");
  const chatHistoryQuery = useChatHistoryQuery(token, canRead && route === "ask");

  const adminEnabled = canRead && isAdmin && route.startsWith("admin");
  const sourcePagesQuery = useSourcePagesQuery(token, adminEnabled);
  const checkpointsQuery = useCheckpointsQuery(token, adminEnabled);
  const adminDocumentsQuery = useAdminDocumentsQuery(token, adminEnabled);
  const adminEventsQuery = useAdminEventsQuery(token, adminEnabled);
  const adminFamiliesQuery = useAdminFamiliesQuery(token, adminEnabled);
  const adminAnalyticsQuery = useAdminAnalyticsQuery(token, adminEnabled);

  /* ---------------- Derived data ---------------- */
  const digestData = digestQuery.data;
  const events = useMemo(() => digestData?.events ?? [], [digestData]);
  const digestDate = digestData?.digest_date ?? "";
  const sources = useMemo(() => sourcesQuery.data ?? [], [sourcesQuery.data]);
  const runs = useMemo(() => runsQuery.data ?? [], [runsQuery.data]);
  const deadlines = useMemo(() => deadlinesQuery.data ?? [], [deadlinesQuery.data]);
  const obligationGroups = useMemo(() => obligationsQuery.data ?? [], [obligationsQuery.data]);
  const stakeholderViews = useMemo(() => stakeholdersQuery.data ?? [], [stakeholdersQuery.data]);
  const readiness = readinessQuery.data ?? null;
  const selectedEvent = eventQuery.data ?? null;
  const sourcePages = useMemo(() => sourcePagesQuery.data ?? [], [sourcePagesQuery.data]);
  const checkpoints = useMemo(() => checkpointsQuery.data ?? [], [checkpointsQuery.data]);
  const adminDocs = useMemo(() => adminDocumentsQuery.data ?? [], [adminDocumentsQuery.data]);
  const adminEvents = useMemo(() => adminEventsQuery.data ?? [], [adminEventsQuery.data]);
  const families = useMemo(() => adminFamiliesQuery.data ?? [], [adminFamiliesQuery.data]);
  const analytics = adminAnalyticsQuery.data ?? null;

  const pipelineStatus: PipelineStatus = healthQuery.isError
    ? "offline"
    : healthQuery.data
      ? healthQuery.data.status === "ok"
        ? "online"
        : "degraded"
      : "offline";

  /* ---------------- Status objects for views ---------------- */
  const digestStatus = statusFrom(digestQuery);
  const subscriptionsStatus = statusFrom(subscriptionsQuery);
  const eventStatus = statusFrom(eventQuery);
  const chatStatus = statusFrom(chatHistoryQuery);
  const deadlinesStatus = statusFrom(deadlinesQuery);
  const obligationsStatus = statusFrom(obligationsQuery);
  const stakeholdersStatus = statusFrom(stakeholdersQuery);
  const readinessStatus = statusFrom(readinessQuery);
  const adminStatus = combineStatus([
    statusFrom(sourcePagesQuery),
    statusFrom(checkpointsQuery),
    statusFrom(adminDocumentsQuery),
    statusFrom(adminEventsQuery),
    statusFrom(adminFamiliesQuery),
    statusFrom(adminAnalyticsQuery),
  ]);

  /* ---------------- Seed editable local state from server ---------------- */
  useEffect(() => {
    if (subscriptionsQuery.data) {
      setSettings(subscriptionsQuery.data);
    }
  }, [subscriptionsQuery.data]);

  useEffect(() => {
    if (chatHistoryQuery.data) {
      setChatMessages(
        chatHistoryQuery.data.map((item) => ({
          role: item.role,
          content: item.content,
          created_at: item.created_at ?? null,
        })),
      );
    }
  }, [chatHistoryQuery.data]);

  // Mark the opened event as read once it loads (fire-and-forget, no UI dependency).
  useEffect(() => {
    const id = eventQuery.data?.id;
    if (!id) return;
    void markRead(id, token).catch(() => undefined);
  }, [eventQuery.data?.id, token]);

  /* ---------------- Computed lists ---------------- */
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

  const sourceByCode = useMemo(
    () => new Map(sources.map((source) => [source.code.toLowerCase(), source])),
    [sources],
  );

  /* ---------------- Mutations ---------------- */
  const bookmarkMutation = useMutation({
    mutationFn: (event: DigestEvent) => toggleBookmark(event.id, token),
    onMutate: (event) => setBusyAction(`bookmark-${event.id}`),
    onSuccess: (result, event) => {
      queryClient.setQueryData<DigestResponse>(queryKeys.digest, (old) =>
        old
          ? {
              ...old,
              events: old.events.map((item) =>
                item.id === event.id ? { ...item, is_bookmarked: result.is_bookmarked } : item,
              ),
            }
          : old,
      );
      queryClient.setQueryData<DigestEvent>(queryKeys.event(event.id), (old) =>
        old ? { ...old, is_bookmarked: result.is_bookmarked } : old,
      );
    },
    onSettled: () => setBusyAction(null),
  });

  const saveSettingsMutation = useMutation({
    mutationFn: () => saveSubscriptions(settings, token),
    onMutate: () => setBusyAction("settings"),
    onSuccess: (saved) => {
      setSettings(saved);
      queryClient.setQueryData(queryKeys.subscriptions, saved);
      setStatusMessage("Notification preferences saved.");
    },
    onError: (error) =>
      setStatusMessage(errorMessage(error, "Unable to save preferences.")),
    onSettled: () => setBusyAction(null),
  });

  const toggleSourceMutation = useMutation({
    mutationFn: (source: SourceHealth) => toggleSource(source, token),
    onMutate: (source) => setBusyAction(`source-${source.id}`),
    onSuccess: (updated) => {
      queryClient.setQueryData<SourceHealth[]>(queryKeys.admin.sources, (old) =>
        old ? old.map((row) => (row.id === updated.id ? updated : row)) : old,
      );
    },
    onError: (error) => setStatusMessage(errorMessage(error, "Unable to update source.")),
    onSettled: () => setBusyAction(null),
  });

  const crawlSourceMutation = useMutation({
    mutationFn: (source: SourceHealth) => crawlSource(source.id, token),
    onMutate: (source) => setBusyAction(`crawl-source-${source.id}`),
    onSuccess: (result) => {
      setStatusMessage(
        `Crawl finished: ${result.docs_found} documents, ${result.new_events} events.`,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.sources });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.runs });
    },
    onError: (error) => setStatusMessage(errorMessage(error, "Unable to start source crawl.")),
    onSettled: () => setBusyAction(null),
  });

  const crawlPageMutation = useMutation({
    mutationFn: (page: SourcePage) => crawlSourcePage(page.id, token),
    onMutate: (page) => setBusyAction(`crawl-page-${page.id}`),
    onSuccess: (result) => {
      setStatusMessage(
        `Page crawl finished: ${result.docs_found} documents, ${result.new_events} events.`,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.digest });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.sources });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.runs });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.pages });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.checkpoints });
    },
    onError: (error) => setStatusMessage(errorMessage(error, "Unable to start page crawl.")),
    onSettled: () => setBusyAction(null),
  });

  const chatMutation = useMutation({
    mutationFn: (message: string) => sendChat(message, selectedEvent?.id ?? null, token),
  });

  /* ---------------- Handlers ---------------- */
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
    queryClient.clear();
  }

  function handleSaveSettings() {
    saveSettingsMutation.mutate();
  }

  function handleBookmark(event: DigestEvent) {
    bookmarkMutation.mutate(event);
  }

  function handleToggleSource(source: SourceHealth) {
    toggleSourceMutation.mutate(source);
  }

  function handleSourceCrawl(source: SourceHealth) {
    crawlSourceMutation.mutate(source);
  }

  function handlePageCrawl(page: SourcePage) {
    crawlPageMutation.mutate(page);
  }

  async function handleAsk(prompt?: string) {
    const message = (prompt ?? chatInput).trim();
    if (!message) return;
    setChatInput("");
    setChatLoading(true);
    const nextMessages: ChatMessage[] = [...chatMessages, { role: "user", content: message }];
    setChatMessages(nextMessages);
    try {
      const response = await chatMutation.mutateAsync(message);
      setChatMessages([...nextMessages, { role: "assistant", content: response.reply }]);
    } catch (error) {
      setChatMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: errorMessage(error, "The assistant could not answer right now."),
        },
      ]);
    } finally {
      setChatLoading(false);
    }
  }

  function loadBaseData() {
    void digestQuery.refetch();
    void subscriptionsQuery.refetch();
    void sourcesQuery.refetch();
    void runsQuery.refetch();
  }

  function loadIntelligenceData() {
    void deadlinesQuery.refetch();
    void obligationsQuery.refetch();
    void stakeholdersQuery.refetch();
    void readinessQuery.refetch();
  }

  const userEmail = session?.user.email ?? (demoMode ? "local-preview@resolven.ai" : "");
  const bootstrapping = canRead && digestQuery.isLoading;
  const loading = !authReady || bootstrapping;

  return {
    route,
    initialEventId,
    session,
    authReady,
    demoMode,
    email,
    password,
    authMessage,
    statusMessage,
    loading,
    busyAction,
    digestDate,
    events,
    selectedEvent,
    sources,
    runs,
    settings,
    isAdmin,
    pipelineStatus,
    query,
    sourceFilter,
    stakeholderFilter,
    eventTypeFilter,
    dateFilter,
    deadlines,
    obligationGroups,
    stakeholderViews,
    readiness,
    intelligenceTab,
    deadlineType,
    deadlineStakeholder,
    chatInput,
    chatMessages,
    chatLoading,
    sourcePages,
    checkpoints,
    adminDocs,
    adminEvents,
    families,
    analytics,
    token,
    canRead,
    userEmail,
    sourceByCode,
    filteredEvents,
    savedEvents,
    activeDeadlines,
    // status objects
    digestStatus,
    subscriptionsStatus,
    eventStatus,
    chatStatus,
    deadlinesStatus,
    obligationsStatus,
    stakeholdersStatus,
    readinessStatus,
    adminStatus,
    // setters
    setEmail,
    setPassword,
    setStatusMessage,
    setDemoMode,
    setSettings,
    setQuery,
    setSourceFilter,
    setStakeholderFilter,
    setEventTypeFilter,
    setDateFilter,
    setIntelligenceTab,
    setDeadlineType,
    setDeadlineStakeholder,
    setChatInput,
    // actions
    loadBaseData,
    loadIntelligenceData,
    handleSignIn,
    handleMagicLink,
    handleSignOut,
    handleSaveSettings,
    handleBookmark,
    handleAsk,
    handleToggleSource,
    handleSourceCrawl,
    handlePageCrawl,
    downloadLatestExport,
  };
}

export type WorkspaceController = ReturnType<typeof useWorkspaceController>;

const WorkspaceContext = createContext<WorkspaceController | null>(null);

export function WorkspaceProvider({
  initialRoute,
  initialEventId,
  children,
}: {
  initialRoute: RouteKey;
  initialEventId?: number;
  children: ReactNode;
}) {
  const controller = useWorkspaceController(initialRoute, initialEventId);
  return <WorkspaceContext.Provider value={controller}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceController {
  const context = useContext(WorkspaceContext);
  if (!context) {
    throw new Error("useWorkspace must be used within a WorkspaceProvider");
  }
  return context;
}
