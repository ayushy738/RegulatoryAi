"use client";

import type { Session } from "@supabase/supabase-js";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
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
  enqueueExistingRagDocuments,
  markRead,
  processRagJobs,
  requeueProcessingRagJobs,
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
  useAdminUsersQuery,
  useChatHistoryQuery,
  useCheckpointsQuery,
  useDeadlinesQuery,
  useDigestQuery,
  useEventQuery,
  useHealthQuery,
  useObligationsQuery,
  useReadinessQuery,
  useRagChunksQuery,
  useRagQueueQuery,
  useRagStatusQuery,
  useRunsQuery,
  useSourcePagesQuery,
  useSourcesQuery,
  useStakeholdersQuery,
  useSubscriptionsQuery,
} from "@/lib/queries";
import { supabase } from "@/lib/supabase";

import { cleanText, eventStakeholders, eventSummary } from "./format";
import { defaultSettings, normalizeRoute } from "./types";
import type {
  ChatMessage,
  EvidenceItem,
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
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [authMessage, setAuthMessage] = useState("");
  const [authModalOpen, setAuthModalOpen] = useState(false);
  const [statusMessage, setStatusMessage] = useState("");
  const [busyAction, setBusyAction] = useState<string | null>(null);
  const authWaiterRef = useRef<{
    resolve: (session: Session) => void;
    reject: (error: Error) => void;
  } | null>(null);

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
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceItem | null>(null);

  const token = session?.access_token;
  const user = session?.user ?? null;
  const isAuthenticated = Boolean(session);
  const canRead = true;

  function resolvePendingAuthentication(nextSession: Session) {
    setSession(nextSession);
    setAuthModalOpen(false);
    setAuthMessage("");
    authWaiterRef.current?.resolve(nextSession);
    authWaiterRef.current = null;
  }

  /* ---------------- Auth ---------------- */
  useEffect(() => {
    if (!supabase) {
      setAuthReady(true);
      return;
    }
    let mounted = true;
    supabase.auth.getSession().then(({ data }) => {
      if (!mounted) return;
      setSession(data.session);
      setAuthReady(true);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, nextSession) => {
      if (nextSession) resolvePendingAuthentication(nextSession);
      else setSession(null);
      setAuthReady(true);
    });
    return () => {
      mounted = false;
      data.subscription.unsubscribe();
    };
  }, []);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    setQuery(params.get("q") ?? "");
    setSourceFilter(params.get("source") ?? "all");
  }, []);

  /* ---------------- Server state (TanStack Query) ---------------- */
  const healthQuery = useHealthQuery();
  const digestQuery = useDigestQuery(token, canRead);
  const subscriptionsQuery = useSubscriptionsQuery(token, isAuthenticated);
  const sourcesQuery = useSourcesQuery(token, isAuthenticated);
  const runsQuery = useRunsQuery(token, isAuthenticated);

  const isAdmin = sourcesQuery.isSuccess && runsQuery.isSuccess;

  const intelligenceEnabled =
    canRead &&
    (route === "intelligence" ||
      route === "deadlines" ||
      route === "dashboard" ||
      route === "event" ||
      route === "saved" ||
      route === "documents");
  const deadlinesQuery = useDeadlinesQuery(token, intelligenceEnabled);
  const obligationsQuery = useObligationsQuery(token, intelligenceEnabled);
  const stakeholdersQuery = useStakeholdersQuery(token, intelligenceEnabled);
  const readinessQuery = useReadinessQuery(token, intelligenceEnabled);

  const eventQuery = useEventQuery(initialEventId, token, canRead && route === "event");
  const chatHistoryQuery = useChatHistoryQuery(token, canRead && (route === "ask" || route === "saved"));

  const adminEnabled =
    canRead &&
    isAdmin &&
    (route.startsWith("admin") || route === "dashboard" || route === "documents" || route === "saved");
  const sourcePagesQuery = useSourcePagesQuery(token, adminEnabled);
  const checkpointsQuery = useCheckpointsQuery(token, adminEnabled);
  const adminDocumentsQuery = useAdminDocumentsQuery(token, adminEnabled);
  const adminEventsQuery = useAdminEventsQuery(token, adminEnabled);
  const adminFamiliesQuery = useAdminFamiliesQuery(token, adminEnabled);
  const adminAnalyticsQuery = useAdminAnalyticsQuery(token, adminEnabled);
  const adminUsersQuery = useAdminUsersQuery(token, adminEnabled);
  const ragEnabled = canRead && isAdmin && (route.startsWith("admin") || route === "dashboard");
  const ragStatusQuery = useRagStatusQuery(token, ragEnabled);
  const ragQueueQuery = useRagQueueQuery(token, ragEnabled);
  const ragChunksQuery = useRagChunksQuery(token, ragEnabled);

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
  const adminUsers = useMemo(() => adminUsersQuery.data ?? [], [adminUsersQuery.data]);
  const ragStatus = ragStatusQuery.data ?? null;
  const ragQueue = useMemo(() => ragQueueQuery.data ?? [], [ragQueueQuery.data]);
  const ragChunks = useMemo(() => ragChunksQuery.data ?? [], [ragChunksQuery.data]);

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
  const ragSystemStatus = combineStatus([
    statusFrom(ragStatusQuery),
    statusFrom(ragQueueQuery),
    statusFrom(ragChunksQuery),
  ]);
  const adminStatus = combineStatus([
    statusFrom(sourcePagesQuery),
    statusFrom(checkpointsQuery),
    statusFrom(adminDocumentsQuery),
    statusFrom(adminEventsQuery),
    statusFrom(adminFamiliesQuery),
    statusFrom(adminAnalyticsQuery),
    statusFrom(adminUsersQuery),
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
          citations: [],
          related_questions: [],
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
      const text = cleanText(
        `${event.title} ${event.issuing_body ?? ""} ${event.topic_tags.join(" ")} ${eventSummary(event)}`,
        "",
      ).toLowerCase();
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
    mutationFn: async () => {
      const authSession = await ensureAuthenticated();
      return saveSubscriptions(settings, authSession.access_token);
    },
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

  const processRagMutation = useMutation({
    mutationFn: () => processRagJobs(token, 1, false),
    onMutate: () => setBusyAction("rag-process"),
    onSuccess: (result) => {
      setStatusMessage(
        `RAG worker processed ${result.processed ?? 0} job(s): ${result.completed ?? 0} completed, ${result.failed ?? 0} failed.`,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragStatus });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragQueue });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragChunks });
    },
    onError: (error) => setStatusMessage(errorMessage(error, "Unable to process RAG queue.")),
    onSettled: () => setBusyAction(null),
  });

  const requeueRagMutation = useMutation({
    mutationFn: () => requeueProcessingRagJobs(token),
    onMutate: () => setBusyAction("rag-requeue"),
    onSuccess: (result) => {
      setStatusMessage(`Requeued ${result.requeued ?? result.processed ?? 0} interrupted RAG job(s).`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragStatus });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragQueue });
    },
    onError: (error) => setStatusMessage(errorMessage(error, "Unable to requeue RAG jobs.")),
    onSettled: () => setBusyAction(null),
  });

  const enqueueRagMutation = useMutation({
    mutationFn: () => enqueueExistingRagDocuments(token),
    onMutate: () => setBusyAction("rag-enqueue"),
    onSuccess: (result) => {
      setStatusMessage(`Queued ${result.enqueued ?? result.processed ?? 0} eligible document(s) for RAG indexing.`);
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragStatus });
      void queryClient.invalidateQueries({ queryKey: queryKeys.admin.ragQueue });
    },
    onError: (error) => setStatusMessage(errorMessage(error, "Unable to enqueue RAG jobs.")),
    onSettled: () => setBusyAction(null),
  });

  /* ---------------- Handlers ---------------- */
  async function login(nextEmail = email, nextPassword = password) {
    setAuthMessage("");
    if (!supabase) {
      const error = new Error("Authentication is not configured.");
      setAuthMessage(error.message);
      throw error;
    }
    const { data, error } = await supabase.auth.signInWithPassword({
      email: nextEmail,
      password: nextPassword,
    });
    if (error) {
      setAuthMessage(error.message);
      throw error;
    }
    const nextSession = data.session ?? (await supabase.auth.getSession()).data.session;
    if (!nextSession) {
      const missingSession = new Error("Sign in succeeded but no session was returned.");
      setAuthMessage(missingSession.message);
      throw missingSession;
    }
    resolvePendingAuthentication(nextSession);
    void queryClient.invalidateQueries({ queryKey: queryKeys.subscriptions });
    return nextSession;
  }

  async function logout() {
    if (supabase) await supabase.auth.signOut();
    setSession(null);
    setAuthModalOpen(false);
    authWaiterRef.current?.reject(new Error("Signed out."));
    authWaiterRef.current = null;
    queryClient.clear();
  }

  async function ensureAuthenticated() {
    if (session) return session;
    if (!supabase) {
      const error = new Error("Authentication is not configured.");
      setAuthMessage(error.message);
      setAuthModalOpen(true);
      throw error;
    }
    const { data, error } = await supabase.auth.getSession();
    if (error) {
      setAuthMessage(error.message);
      throw error;
    }
    if (data.session) {
      setSession(data.session);
      return data.session;
    }
    authWaiterRef.current?.reject(new Error("A newer sign-in request replaced this one."));
    setAuthMessage("Sign in to save notification preferences.");
    setAuthModalOpen(true);
    return new Promise<Session>((resolve, reject) => {
      authWaiterRef.current = { resolve, reject };
    });
  }

  function closeAuthModal() {
    authWaiterRef.current?.reject(new Error("Sign in cancelled."));
    authWaiterRef.current = null;
    setAuthModalOpen(false);
    setAuthMessage("");
  }

  async function handleSignIn() {
    await login().catch(() => undefined);
  }

  async function handleMagicLink() {
    setAuthMessage("");
    if (!supabase) {
      setAuthMessage("Authentication is not configured.");
      return;
    }
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: { emailRedirectTo: window.location.origin },
    });
    setAuthMessage(error ? error.message : "Magic link sent. Check your inbox.");
  }

  async function handleSignOut() {
    await logout();
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
      setChatMessages([
        ...nextMessages,
        {
          role: "assistant",
          content: response.reply,
          intent: response.intent ?? null,
          citations: response.citations ?? [],
          related_questions: response.related_questions ?? [],
          model: response.model,
        },
      ]);
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

  function loadRagData() {
    void ragStatusQuery.refetch();
    void ragQueueQuery.refetch();
    void ragChunksQuery.refetch();
  }

  function handleProcessRagJob() {
    processRagMutation.mutate();
  }

  function handleRequeueRagJobs() {
    requeueRagMutation.mutate();
  }

  function handleEnqueueRagDocuments() {
    enqueueRagMutation.mutate();
  }

  const userEmail = session?.user.email ?? "";
  const bootstrapping = canRead && digestQuery.isLoading;
  const loading = !authReady || bootstrapping;

  return {
    route,
    initialEventId,
    session,
    user,
    isAuthenticated,
    authReady,
    email,
    password,
    authMessage,
    authModalOpen,
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
    adminUsers,
    ragStatus,
    ragQueue,
    ragChunks,
    token,
    canRead,
    userEmail,
    sourceByCode,
    filteredEvents,
    savedEvents,
    activeDeadlines,
    selectedEvidence,
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
    ragSystemStatus,
    // setters
    setEmail,
    setPassword,
    setStatusMessage,
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
    setSelectedEvidence,
    // actions
    loadBaseData,
    loadIntelligenceData,
    loadRagData,
    handleSignIn,
    handleMagicLink,
    handleSignOut,
    login,
    logout,
    ensureAuthenticated,
    closeAuthModal,
    handleSaveSettings,
    handleBookmark,
    handleAsk,
    handleProcessRagJob,
    handleRequeueRagJobs,
    handleEnqueueRagDocuments,
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
