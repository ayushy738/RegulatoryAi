import { useEffect, useRef, useState } from "react";
import {
  Bot,
  Bookmark,
  Clipboard,
  Copy,
  FileSearch,
  MessageSquareText,
  RefreshCw,
  Search,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  UserCircle,
} from "lucide-react";

import { MarkdownLite } from "@/app/components/ui/MarkdownLite";
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
  const transcriptRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const latestUser = [...chatMessages].reverse().find((message) => message.role === "user");
  const latestAssistant = [...chatMessages].reverse().find((message) => message.role === "assistant");
  const conversations = chatMessages.filter((message) => message.role === "user");

  useEffect(() => {
    transcriptRef.current?.scrollTo({ top: transcriptRef.current.scrollHeight, behavior: "smooth" });
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

  function saveQuestion(message: ChatMessage) {
    void navigator.clipboard?.writeText(message.content);
    setStatusMessage("Question copied for reuse.");
  }

  function submitPrompt() {
    void handleAsk();
  }

  return (
    <section className="ask-premium-page ops-page">
      <aside className="conversation-sidebar">
        <div className="conversation-sidebar-header">
          <h2>Sessions</h2>
          <button type="button" aria-label="Search conversations">
            <Search size={16} />
          </button>
        </div>
        <label className="conversation-search">
          <Search size={15} />
          <input placeholder="Search history" aria-label="Search conversation history" />
        </label>
        <div className="conversation-list">
          {conversations.slice(-14).reverse().map((message, index) => (
            <button key={`${message.content}-${index}`} type="button" onClick={() => setChatInput(message.content)}>
              <MessageSquareText size={16} />
              <span>{stripMarkdownNoise(message.content).slice(0, 86)}</span>
            </button>
          ))}
          {!conversations.length ? <p className="muted">No conversation history yet.</p> : null}
        </div>
      </aside>

      <main className="ask-workbench">
        <header className="ask-premium-header">
          <div>
            <span>
              <Sparkles size={16} />
              Grounded Regulatory Assistant
            </span>
            <h1>Ask AI</h1>
            <p>Ask about deadlines, obligations, amendments, consultations, stakeholders, or source evidence.</p>
          </div>
          {latestAssistant ? (
            <div className="answer-health">
              <strong>{latestAssistant.citations?.length ?? 0}</strong>
              <span>citations in latest answer</span>
            </div>
          ) : null}
        </header>

        {!chatMessages.length ? (
          <div className="ask-start-panel">
            <Bot size={24} />
            <h2>Start with an evidence-backed regulatory question.</h2>
            <div className="ask-suggestions premium-suggestions">
              {suggestedPrompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => void handleAsk(prompt)} disabled={chatLoading}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        ) : null}

        <section className="ask-transcript premium-transcript" aria-live="polite" ref={transcriptRef}>
          {chatStatus.isLoading && !chatMessages.length ? (
            <article className="assistant-empty">
              <RefreshCw className="spin" size={22} />
              <p>Loading conversation history...</p>
            </article>
          ) : null}

          {chatMessages.map((message, index) =>
            message.role === "user" ? (
              <article className="chat-turn user-turn" key={`${message.role}-${index}`}>
                <div className="user-bubble">
                  <span>You</span>
                  <p>{cleanText(message.content)}</p>
                </div>
                <UserCircle size={22} />
              </article>
            ) : (
              <article className="chat-turn assistant-turn" key={`${message.role}-${index}`}>
                <div className="assistant-avatar">
                  <Bot size={19} />
                </div>
                <div className="assistant-answer-block">
                  <div className="assistant-answer-meta">
                    <span>Resolven AI</span>
                    {message.intent ? <strong>{message.intent}</strong> : null}
                    {message.model ? <small>{message.model}</small> : null}
                  </div>
                  <MarkdownLite content={message.content} />
                  <Citations message={message} setSelectedEvidence={setSelectedEvidence} />
                  {message.related_questions?.length ? (
                    <div className="related-questions premium-related">
                      {message.related_questions.map((question) => (
                        <button key={question} type="button" onClick={() => void handleAsk(question)} disabled={chatLoading}>
                          {question}
                        </button>
                      ))}
                    </div>
                  ) : null}
                  <footer className="chat-actions premium-chat-actions">
                    <button
                      type="button"
                      className={feedback[index] === "up" ? "active" : ""}
                      onClick={() => setFeedback({ ...feedback, [index]: "up" })}
                    >
                      <ThumbsUp size={15} />
                      Helpful
                    </button>
                    <button
                      type="button"
                      className={feedback[index] === "down" ? "active" : ""}
                      onClick={() => setFeedback({ ...feedback, [index]: "down" })}
                    >
                      <ThumbsDown size={15} />
                      Needs work
                    </button>
                    <button type="button" onClick={() => copyAnswer(message)}>
                      <Copy size={15} />
                      Copy
                    </button>
                    <button type="button" onClick={() => latestUser && void handleAsk(latestUser.content)} disabled={chatLoading}>
                      <RefreshCw size={15} />
                      Regenerate
                    </button>
                  </footer>
                </div>
              </article>
            ),
          )}

          {chatLoading ? (
            <article className="chat-turn assistant-turn streaming">
              <div className="assistant-avatar">
                <Bot size={19} />
              </div>
              <div className="assistant-answer-block loading-answer">
                <div className="assistant-answer-meta">
                  <span>Resolven AI</span>
                  <strong>retrieving evidence</strong>
                </div>
                <div className="retrieval-steps">
                  <span>Chunks</span>
                  <span>Graph facts</span>
                  <span>Citations</span>
                </div>
                <p>
                  <RefreshCw className="spin" size={15} />
                  Building an evidence-backed answer...
                </p>
              </div>
            </article>
          ) : null}
        </section>

        <form
          className="ask-composer-pro premium-composer"
          onSubmit={(event) => {
            event.preventDefault();
            submitPrompt();
          }}
        >
          <Clipboard size={18} />
          <textarea
            ref={textareaRef}
            value={chatInput}
            onChange={(event) => setChatInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey) {
                event.preventDefault();
                if (!chatLoading && chatInput.trim()) submitPrompt();
              }
            }}
            placeholder="Ask about deadlines, obligations, consultations, amendments, or stakeholder impact"
            rows={1}
          />
          <button type="button" onClick={() => latestUser && saveQuestion(latestUser)} disabled={!latestUser}>
            <Bookmark size={17} />
          </button>
          <button type="submit" disabled={chatLoading || !chatInput.trim()}>
            <Send size={18} />
          </button>
        </form>
      </main>
    </section>
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
      <div className="insufficient-evidence premium-insufficient">
        <FileSearch size={16} />
        No structured citations were returned for this answer. Treat it as insufficient evidence until a cited retrieval
        result is available.
      </div>
    );
  }
  return (
    <div className="citation-grid premium-citation-grid">
      {message.citations.slice(0, 8).map((citation, citationIndex) => (
        <button
          type="button"
          key={`${citation.document_id}-${citation.chunk_id}-${citationIndex}`}
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
              relationships: citation.section_title ? [`Section: ${citation.section_title}`] : [],
            })
          }
        >
          <strong>{citationIndex + 1}. {citation.title}</strong>
          <span>
            {citation.issuer ?? "Unknown issuer"} | chunk {citation.chunk_id ?? "graph"}
          </span>
        </button>
      ))}
    </div>
  );
}
