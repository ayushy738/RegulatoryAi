"use client";

import { Menu, Plus, Send, X } from "lucide-react";
import {
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
} from "react";

import { MarkdownLite } from "@/app/components/ui/MarkdownLite";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import {
  getChatConversation,
  listChatConversations,
  sendChat,
} from "@/lib/api";
import type { ChatResponse } from "@/lib/schemas";

type CitationCard = {
  title?: string | null;
  issuer?: string | null;
  issue_date?: string | null;
  source_url?: string | null;
  section_title?: string | null;
  page_number?: number | null;
  evidence?: string | null;
};

type ChatTurn = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations?: CitationCard[];
  knowledgeBasis?: "official" | "general" | "none";
  pending?: boolean;
  error?: boolean;
};

type ConversationSummary = {
  id: string;
  title: string;
  updatedAt: number | null;
};

const EXAMPLE_PROMPTS = [
  "How does DSM regulation affect DISCOMs?",
  "What are the latest CERC interconnection obligations?",
  "What compliance duties apply to renewable generators?",
];

function titleFromQuestion(question: string): string {
  let cleaned = question.trim().replace(/\s+/g, " ");
  cleaned = cleaned.replace(
    /^(what|how|why|when|where|which|who|can|could|does|do|is|are|explain|tell me|please)\b[\s,:-]*/i,
    "",
  );
  cleaned = cleaned.replace(/\?+$/, "").trim();
  if (!cleaned) {
    cleaned = question.trim().replace(/\s+/g, " ");
  }
  if (!cleaned) return "New chat";
  const titled = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return titled.length <= 72 ? titled : `${titled.slice(0, 69).trim()}…`;
}

function formatCitation(citation: CitationCard): string {
  const issuer = citation.issuer?.trim() || "Official source";
  const date = citation.issue_date?.trim();
  return date ? `${issuer} · ${date}` : issuer;
}

function displayContent(content: string, hasCitations: boolean): string {
  if (!hasCitations) return content;
  return content.replace(/\n*Sources\s*\n(?:\d+\..*(?:\n {3}.*)*)+/i, "").trim();
}

function toTimestamp(value: string | number | null | undefined): number | null {
  if (value == null) return null;
  if (typeof value === "number") return value;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function dayBucket(timestamp: number | null): string {
  if (timestamp == null) return "Earlier";
  const now = new Date();
  const day = new Date(timestamp);
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startDay = new Date(day.getFullYear(), day.getMonth(), day.getDate());
  const diffDays = Math.round(
    (startToday.getTime() - startDay.getTime()) / 86_400_000,
  );
  if (diffDays <= 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return "Previous 7 days";
  return "Earlier";
}

export function AskConversationWorkspace() {
  const { token } = useWorkspace();
  const generatedId = useId().replaceAll(":", "");
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const submitLockRef = useRef(false);
  const [navOpen, setNavOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [historyQuery, setHistoryQuery] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<CitationCard | null>(
    null,
  );

  const refreshConversations = useCallback(async () => {
    if (!token) return;
    try {
      const rows = await listChatConversations(token);
      setConversations(
        rows.map((row) => ({
          id: row.id,
          title: row.title?.trim() || "Untitled chat",
          updatedAt: toTimestamp(row.last_message_at ?? row.updated_at),
        })),
      );
    } catch {
      // Keep the chat usable even if the sidebar fails to refresh.
    }
  }, [token]);

  const loadConversation = useCallback(
    async (id: string, { pushUrl = true }: { pushUrl?: boolean } = {}) => {
      if (!token) return;
      setLoadError(null);
      setSelectedCitation(null);
      try {
        const detail = await getChatConversation(id, token);
        setSessionId(detail.id);
        setTurns(
          detail.messages.map((message) => ({
            id: String(message.id),
            role: message.role,
            content: message.content,
            citations: message.citations ?? [],
            // Answers written before knowledge_basis was persisted fall back to
            // inferring it from their restored citations.
            knowledgeBasis:
              message.knowledge_basis ??
              ((message.citations?.length ?? 0) > 0 ? "official" : undefined),
          })),
        );
        if (pushUrl) {
          const url = new URL(window.location.href);
          url.searchParams.set("session", id);
          window.history.pushState({ session: id }, "", url.toString());
        }
        setNavOpen(false);
      } catch {
        setLoadError("This conversation could not be opened.");
      }
    },
    [token],
  );

  useEffect(() => {
    void refreshConversations();
  }, [refreshConversations]);

  useEffect(() => {
    const restore = () => {
      const id = new URLSearchParams(window.location.search).get("session");
      if (id && id.trim()) {
        void loadConversation(id.trim(), { pushUrl: false });
      }
    };
    restore();
    window.addEventListener("popstate", restore);
    return () => window.removeEventListener("popstate", restore);
  }, [loadConversation]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [turns.length, submitting]);

  useEffect(() => {
    const el = composerRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 160)}px`;
  }, [draft]);

  function startNewChat() {
    setSessionId(null);
    setTurns([]);
    setDraft("");
    setLoadError(null);
    setSelectedCitation(null);
    submitLockRef.current = false;
    const url = new URL(window.location.href);
    url.searchParams.delete("session");
    window.history.pushState({}, "", `${url.pathname}${url.search}${url.hash}`);
    setNavOpen(false);
    composerRef.current?.focus();
  }

  async function submitQuestion(question: string) {
    const trimmed = question.trim();
    if (!token || !trimmed || submitLockRef.current || submitting) return;
    submitLockRef.current = true;
    setSubmitting(true);
    setLoadError(null);

    const userTurn: ChatTurn = {
      id: `local-user-${Date.now()}`,
      role: "user",
      content: trimmed,
    };
    const pendingId = `local-assistant-${Date.now()}`;
    setTurns((current) => [
      ...current,
      userTurn,
      {
        id: pendingId,
        role: "assistant",
        content: "Researching regulatory sources…",
        pending: true,
      },
    ]);
    setDraft("");

    try {
      const response: ChatResponse = await sendChat(
        trimmed,
        null,
        token,
        sessionId,
      );
      const nextSessionId = response.session_id ?? sessionId;
      if (nextSessionId) {
        setSessionId(nextSessionId);
        const url = new URL(window.location.href);
        url.searchParams.set("session", nextSessionId);
        window.history.replaceState(
          { session: nextSessionId },
          "",
          url.toString(),
        );
        setConversations((current) => {
          const existing = current.find((item) => item.id === nextSessionId);
          if (existing) {
            return [
              {
                ...existing,
                title: existing.title || titleFromQuestion(trimmed),
                updatedAt: Date.now(),
              },
              ...current.filter((item) => item.id !== nextSessionId),
            ];
          }
          return [
            {
              id: nextSessionId,
              title: titleFromQuestion(trimmed),
              updatedAt: Date.now(),
            },
            ...current,
          ];
        });
      }
      setTurns((current) =>
        current.map((turn) =>
          turn.id === pendingId
            ? {
                id: pendingId,
                role: "assistant",
                content: response.reply,
                citations: response.citations ?? [],
                knowledgeBasis: response.knowledge_basis,
              }
            : turn,
        ),
      );
      void refreshConversations();
    } catch {
      setTurns((current) =>
        current.map((turn) =>
          turn.id === pendingId
            ? {
                id: pendingId,
                role: "assistant",
                content:
                  "Something went wrong while researching this question. You can retry your question.",
                error: true,
              }
            : turn,
        ),
      );
    } finally {
      setSubmitting(false);
      submitLockRef.current = false;
    }
  }

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await submitQuestion(draft);
  }

  function onComposerKeyDown(event: ReactKeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      if (draft.trim() && !submitting) {
        event.currentTarget.form?.requestSubmit();
      }
    }
  }

  const groupedConversations = useMemo(() => {
    const needle = historyQuery.trim().toLowerCase();
    const filtered = conversations.filter((item) =>
      needle ? item.title.toLowerCase().includes(needle) : true,
    );
    const groups: { label: string; items: ConversationSummary[] }[] = [];
    for (const item of filtered) {
      const label = dayBucket(item.updatedAt);
      const existing = groups.find((group) => group.label === label);
      if (existing) existing.items.push(item);
      else groups.push({ label, items: [item] });
    }
    return groups;
  }, [conversations, historyQuery]);

  const empty = turns.length === 0 && !submitting;
  const sendEnabled = Boolean(token) && draft.trim().length > 0 && !submitting;
  const activeTitle =
    conversations.find((item) => item.id === sessionId)?.title ?? "New chat";

  return (
    <div className="ask-chat-shell">
      <aside
        className="ask-chat-sidebar"
        data-open={navOpen ? "true" : "false"}
        aria-label="Conversation history"
      >
        <div className="ask-chat-sidebar-header">
          <button type="button" className="ask-chat-new" onClick={startNewChat}>
            <Plus size={16} aria-hidden="true" />
            New chat
          </button>
          <button
            type="button"
            className="ask-chat-sidebar-close"
            aria-label="Close conversations"
            onClick={() => setNavOpen(false)}
          >
            <X size={18} />
          </button>
        </div>
        <label className="ask-chat-visually-hidden" htmlFor={`ask-history-${generatedId}`}>
          Search conversations
        </label>
        <input
          id={`ask-history-${generatedId}`}
          className="ask-chat-history-search"
          type="search"
          placeholder="Search conversations"
          value={historyQuery}
          onChange={(event) => setHistoryQuery(event.target.value)}
        />
        <div className="ask-chat-conversation-list">
          {groupedConversations.length === 0 ? (
            <p className="ask-chat-muted">Your conversations will appear here.</p>
          ) : (
            groupedConversations.map((group) => (
              <nav
                key={group.label}
                className="ask-chat-group"
                aria-label={group.label}
              >
                <h2 className="ask-chat-group-label">{group.label}</h2>
                <ul>
                  {group.items.map((conversation) => (
                    <li key={conversation.id}>
                      <button
                        type="button"
                        className={
                          conversation.id === sessionId
                            ? "ask-chat-conversation active"
                            : "ask-chat-conversation"
                        }
                        aria-current={
                          conversation.id === sessionId ? "true" : undefined
                        }
                        onClick={() => void loadConversation(conversation.id)}
                      >
                        {conversation.title}
                      </button>
                    </li>
                  ))}
                </ul>
              </nav>
            ))
          )}
        </div>
      </aside>

      <section className="ask-chat-main" aria-label="Ask AI conversation">
        <div className="ask-chat-mobile-bar">
          <button
            type="button"
            aria-label="Open conversations"
            onClick={() => setNavOpen(true)}
          >
            <Menu size={18} />
          </button>
          <strong className="ask-chat-mobile-title">{activeTitle}</strong>
          <button type="button" onClick={startNewChat} aria-label="New chat">
            <Plus size={18} />
          </button>
        </div>

        <div className="ask-chat-transcript" ref={transcriptRef}>
          {loadError ? <p className="ask-chat-error">{loadError}</p> : null}
          {empty ? (
            <div className="ask-chat-empty">
              <h1>Regulatory AI</h1>
              <p className="ask-chat-empty-lead">What can I help you research?</p>
              <p className="ask-chat-muted">
                Ask about regulations, obligations, deadlines, amendments,
                compliance, entities, or regulatory developments.
              </p>
              <div className="ask-chat-examples">
                {EXAMPLE_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    onClick={() => {
                      setDraft(prompt);
                      composerRef.current?.focus();
                    }}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            turns.map((turn) => {
              const citations = turn.citations ?? [];
              return (
                <article
                  key={turn.id}
                  className={
                    turn.role === "user"
                      ? "ask-chat-turn user"
                      : turn.error
                        ? "ask-chat-turn assistant error"
                        : "ask-chat-turn assistant"
                  }
                >
                  <div className="ask-chat-turn-label">
                    {turn.role === "user" ? "You" : "Regulatory AI"}
                  </div>
                  <div className="ask-chat-turn-body">
                    {turn.role === "assistant" ? (
                      <MarkdownLite
                        content={displayContent(
                          turn.content,
                          citations.length > 0,
                        )}
                      />
                    ) : (
                      <p>{turn.content}</p>
                    )}
                  </div>
                  {turn.role === "assistant" &&
                  turn.knowledgeBasis === "general" ? (
                    <p className="ask-chat-basis">
                      General knowledge explanation — no sufficiently relevant
                      official corpus evidence was selected for this answer.
                    </p>
                  ) : null}
                  {turn.role === "assistant" &&
                  turn.knowledgeBasis === "none" ? (
                    <p className="ask-chat-basis">
                      I couldn&apos;t find a sufficiently relevant official
                      regulatory source for this question.
                    </p>
                  ) : null}
                  {citations.length > 0 ? (
                    <div className="ask-chat-sources">
                      <h3>Sources</h3>
                      <ul>
                        {citations.map((citation, index) => (
                          <li key={`${turn.id}-cite-${index}`}>
                            <button
                              type="button"
                              onClick={() => setSelectedCitation(citation)}
                            >
                              <strong>
                                {citation.title || `Source ${index + 1}`}
                              </strong>
                              <span>{formatCitation(citation)}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </article>
              );
            })
          )}
        </div>

        <form className="ask-chat-composer" onSubmit={onSubmit}>
          <label
            className="ask-chat-visually-hidden"
            htmlFor={`ask-composer-${generatedId}`}
          >
            Ask anything about Indian regulation
          </label>
          <textarea
            id={`ask-composer-${generatedId}`}
            ref={composerRef}
            value={draft}
            rows={1}
            placeholder="Ask anything about Indian regulation…"
            disabled={!token || submitting}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={onComposerKeyDown}
          />
          <button type="submit" disabled={!sendEnabled} aria-label="Send">
            <Send size={18} aria-hidden="true" />
          </button>
        </form>
        <p className="ask-chat-composer-hint">
          Enter to send · Shift+Enter for a new line
        </p>
      </section>

      {selectedCitation ? (
        <aside className="ask-chat-evidence" aria-label="Source details">
          <div className="ask-chat-evidence-header">
            <h2>Source</h2>
            <button
              type="button"
              aria-label="Close source"
              onClick={() => setSelectedCitation(null)}
            >
              <X size={18} />
            </button>
          </div>
          <h3>{selectedCitation.title || "Official source"}</h3>
          <p>{formatCitation(selectedCitation)}</p>
          {selectedCitation.section_title ? (
            <p>Section: {selectedCitation.section_title}</p>
          ) : null}
          {selectedCitation.page_number != null ? (
            <p>Page: {selectedCitation.page_number}</p>
          ) : null}
          {selectedCitation.evidence ? (
            <blockquote className="ask-chat-excerpt">
              {selectedCitation.evidence}
            </blockquote>
          ) : null}
          {selectedCitation.source_url ? (
            <a
              href={selectedCitation.source_url}
              target="_blank"
              rel="noreferrer"
            >
              Open source
            </a>
          ) : null}
        </aside>
      ) : null}
    </div>
  );
}
