"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  Bot,
  Bookmark,
  Copy,
  FileSearch,
  History,
  MessageSquareText,
  RefreshCw,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
} from "lucide-react";

import { Badge } from "@/app/components/ui/Badge";
import { Button, IconButton } from "@/app/components/ui/Button";
import { EmptyState } from "@/app/components/ui/EmptyState";
import { MarkdownLite } from "@/app/components/ui/MarkdownLite";
import { Overlay } from "@/app/components/ui/Overlay";
import { SearchInput } from "@/app/components/ui/Toolbar";
import { cleanText, stripMarkdownNoise } from "@/app/workspace/format";
import { suggestedPrompts } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { ChatMessage } from "@/app/workspace/types";

export function AskView() {
  const {
    chatMessages,
    chatInput,
    setChatInput,
    chatLoading,
    handleAsk,
    chatStatus,
    setSelectedEvidence,
    setStatusMessage,
  } = useWorkspace();

  const [feedback, setFeedback] = useState<Record<number, "up" | "down">>({});
  const [historyQuery, setHistoryQuery] = useState("");
  const [historyOpen, setHistoryOpen] = useState(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  const latestUser = [...chatMessages].reverse().find((message) => message.role === "user");
  const latestAssistant = [...chatMessages]
    .reverse()
    .find((message) => message.role === "assistant");

  const history = useMemo(() => {
    const questions = chatMessages.filter((message) => message.role === "user");
    const needle = historyQuery.trim().toLowerCase();
    const filtered = needle
      ? questions.filter((message) => message.content.toLowerCase().includes(needle))
      : questions;
    return filtered.slice(-20).reverse();
  }, [chatMessages, historyQuery]);

  useEffect(() => {
    transcriptRef.current?.scrollTo({
      top: transcriptRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [chatMessages.length, chatLoading]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = "0px";
    textarea.style.height = `${Math.min(textarea.scrollHeight, 180)}px`;
  }, [chatInput]);

  function copyAnswer(message: ChatMessage) {
    void navigator.clipboard?.writeText(message.content);
    setStatusMessage("Answer copied.");
  }

  const historyPanel = (
    <div className="rv-ask__history">
      <SearchInput
        label="Search question history"
        placeholder="Search history"
        value={historyQuery}
        onChange={setHistoryQuery}
      />
      {history.length ? (
        <ul className="rv-mini-list">
          {history.map((message, index) => (
            <li key={`${message.content}-${index}`}>
              <button
                type="button"
                className="rv-ask__history-item"
                onClick={() => {
                  setChatInput(message.content);
                  setHistoryOpen(false);
                  textareaRef.current?.focus();
                }}
              >
                <MessageSquareText size={14} aria-hidden />
                <span>{stripMarkdownNoise(message.content).slice(0, 90)}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="rv-helper">
          {historyQuery ? "No question matches that search." : "No questions yet."}
        </p>
      )}
    </div>
  );

  return (
    <div className="rv-ask">
      <aside className="rv-ask__side" aria-label="Question history">
        <h2 className="rv-section-title">Sessions</h2>
        {historyPanel}
      </aside>

      <main className="rv-ask__main">
        <header className="rv-ask__header">
          <div className="rv-page-header__text">
            <p className="rv-eyebrow">
              <Sparkles size={12} aria-hidden /> Grounded regulatory assistant
            </p>
            <h1 className="rv-page-title">Ask AI</h1>
            <p className="rv-page-subtitle">
              Ask about deadlines, amendments, consultations, stakeholders or source evidence.
              Answers cite the documents they came from.
            </p>
          </div>
          <div className="rv-ask__header-actions">
            {latestAssistant ? (
              <Badge tone={latestAssistant.citations?.length ? "success" : "warning"}>
                {`${latestAssistant.citations?.length ?? 0} citations in latest answer`}
              </Badge>
            ) : null}
            <Button
              variant="secondary"
              size="sm"
              Icon={History}
              className="rv-ask__history-toggle"
              onClick={() => setHistoryOpen(true)}
            >
              History
            </Button>
          </div>
        </header>

        {!chatMessages.length && !chatStatus.isLoading ? (
          <div className="rv-card rv-ask__starter">
            <h2 className="rv-card-title">Start with an evidence-backed question</h2>
            <p className="rv-helper">
              Every answer is grounded in crawled regulatory documents. Pick a prompt or write
              your own.
            </p>
            <div className="rv-ask__suggestions">
              {suggestedPrompts.map((prompt) => (
                <button
                  key={prompt}
                  type="button"
                  onClick={() => void handleAsk(prompt)}
                  disabled={chatLoading}
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <section className="rv-ask__transcript" aria-live="polite" ref={transcriptRef}>
          {chatStatus.isLoading && !chatMessages.length ? (
            <p className="rv-helper">Loading conversation history…</p>
          ) : null}

          {chatMessages.map((message, index) =>
            message.role === "user" ? (
              <article className="rv-turn rv-turn--user" key={`${message.role}-${index}`}>
                <p>{cleanText(message.content)}</p>
              </article>
            ) : (
              <article className="rv-turn rv-turn--ai" key={`${message.role}-${index}`}>
                <div className="rv-turn__avatar" aria-hidden>
                  <Bot size={16} />
                </div>
                <div className="rv-turn__body">
                  <div className="rv-turn__meta">
                    <span className="rv-cell-primary">Resolven AI</span>
                    {message.intent ? <Badge>{message.intent}</Badge> : null}
                    {message.model ? <span className="rv-meta">{message.model}</span> : null}
                  </div>
                  <MarkdownLite content={message.content} />
                  <Citations message={message} setSelectedEvidence={setSelectedEvidence} />
                  {message.related_questions?.length ? (
                    <div className="rv-ask__suggestions">
                      {message.related_questions.map((question) => (
                        <button
                          key={question}
                          type="button"
                          onClick={() => void handleAsk(question)}
                          disabled={chatLoading}
                        >
                          {question}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <footer className="rv-turn__actions">
                    <Button
                      variant="ghost"
                      size="sm"
                      Icon={ThumbsUp}
                      aria-pressed={feedback[index] === "up"}
                      onClick={() => setFeedback({ ...feedback, [index]: "up" })}
                    >
                      Helpful
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      Icon={ThumbsDown}
                      aria-pressed={feedback[index] === "down"}
                      onClick={() => setFeedback({ ...feedback, [index]: "down" })}
                    >
                      Needs work
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      Icon={Copy}
                      onClick={() => copyAnswer(message)}
                    >
                      Copy
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      Icon={RefreshCw}
                      disabled={chatLoading || !latestUser}
                      onClick={() => latestUser && void handleAsk(latestUser.content)}
                    >
                      Regenerate
                    </Button>
                  </footer>
                </div>
              </article>
            ),
          )}

          {chatLoading ? (
            <article className="rv-turn rv-turn--ai">
              <div className="rv-turn__avatar" aria-hidden>
                <Bot size={16} />
              </div>
              <div className="rv-turn__body">
                <div className="rv-turn__meta">
                  <span className="rv-cell-primary">Resolven AI</span>
                  <Badge tone="info">retrieving evidence</Badge>
                </div>
                <div className="rv-skeleton-stack" aria-hidden>
                  <span className="rv-skeleton" style={{ width: "90%" }} />
                  <span className="rv-skeleton" style={{ width: "75%" }} />
                  <span className="rv-skeleton" style={{ width: "60%" }} />
                </div>
                <p className="rv-helper">Building an evidence-backed answer...</p>
              </div>
            </article>
          ) : null}
        </section>

        <form
          className="rv-composer"
          onSubmit={(event) => {
            event.preventDefault();
            void handleAsk();
          }}
        >
          <label className="rv-visually-hidden" htmlFor="ask-input">
            Ask a regulatory question
          </label>
          <textarea
            id="ask-input"
            ref={textareaRef}
            value={chatInput}
            onChange={(event) => setChatInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (!chatLoading && chatInput.trim()) void handleAsk();
              }
            }}
            placeholder="Ask about deadlines, consultations, amendments or stakeholder impact"
            rows={1}
          />
          <div className="rv-composer__actions">
            <IconButton
              label="Copy last question for reuse"
              Icon={Bookmark}
              variant="ghost"
              disabled={!latestUser}
              onClick={() => {
                if (!latestUser) return;
                void navigator.clipboard?.writeText(latestUser.content);
                setStatusMessage("Question copied for reuse.");
              }}
            />
            <Button
              type="submit"
              Icon={Send}
              loading={chatLoading}
              disabled={!chatInput.trim()}
            >
              Ask
            </Button>
          </div>
        </form>
      </main>

      {historyOpen ? (
        <Overlay
          open
          variant="drawer"
          title="Question history"
          onClose={() => setHistoryOpen(false)}
        >
          {historyPanel}
        </Overlay>
      ) : null}
    </div>
  );
}

function Citations({
  message,
  setSelectedEvidence,
}: {
  message: ChatMessage;
  setSelectedEvidence: ReturnType<typeof useWorkspace>["setSelectedEvidence"];
}) {
  if (!message.citations?.length) {
    return (
      <EmptyState
        compact
        title="No structured citations"
        body="Treat this answer as insufficient evidence until a cited retrieval result is available."
        Icon={FileSearch}
      />
    );
  }
  return (
    <ol className="rv-citations">
      {message.citations.slice(0, 8).map((citation, citationIndex) => (
        <li key={`${citation.document_id}-${citation.chunk_id}-${citationIndex}`}>
          <button
            type="button"
            onClick={() =>
              setSelectedEvidence({
                title: citation.title,
                issuer: citation.issuer,
                date: citation.issue_date,
                evidence: citation.evidence,
                sourceUrl: citation.source_url,
                documentId: citation.document_id,
                chunkId: citation.chunk_id,
                pageNumber: citation.page_number,
                relationships: citation.section_title
                  ? [`Section: ${citation.section_title}`]
                  : [],
              })
            }
          >
            <span className="rv-cell-primary">
              {citationIndex + 1}. {citation.title}
            </span>
            <span className="rv-meta">
              {citation.issuer ?? "Unknown issuer"}
              {citation.chunk_id ? ` · chunk ${citation.chunk_id}` : " · graph fact"}
            </span>
          </button>
        </li>
      ))}
    </ol>
  );
}
