import { MarkdownLite } from "@/app/components/ui/MarkdownLite";
import { stripMarkdownNoise } from "@/app/workspace/format";
import { suggestedPrompts } from "@/app/workspace/nav";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";

function MaterialIcon({ children, filled = false }: { children: string; filled?: boolean }) {
  return (
    <span className="material-symbols-outlined" style={filled ? { fontVariationSettings: "'FILL' 1" } : undefined}>
      {children}
    </span>
  );
}

export function AskView() {
  const {
    chatMessages,
    chatInput,
    setChatInput,
    chatLoading,
    handleAsk,
    chatStatus,
  } = useWorkspace();
  const latestUser = [...chatMessages].reverse().find((message) => message.role === "user");
  const latestAssistant = [...chatMessages].reverse().find((message) => message.role === "assistant");

  return (
    <section className="stitch-ask-page">
      <div className="stitch-chat-frame">
        <main className="stitch-chat-transcript">
          {chatStatus.isLoading && !chatMessages.length ? (
            <div className="stitch-assistant-message">
              <MaterialIcon>sync</MaterialIcon>
              <p>Loading conversation history...</p>
            </div>
          ) : null}

          {latestUser ? (
            <article className="stitch-user-message">
              <div className="stitch-message-avatar user">
                <MaterialIcon>person</MaterialIcon>
              </div>
              <div>
                <span>You</span>
                <p>{latestUser.content}</p>
              </div>
            </article>
          ) : (
            <article className="stitch-user-message muted">
              <div className="stitch-message-avatar user">
                <MaterialIcon>person</MaterialIcon>
              </div>
              <div>
                <span>You</span>
                <p>Ask a regulatory question to begin.</p>
              </div>
            </article>
          )}

          <article className="stitch-assistant-message">
            <div className="stitch-message-avatar ai">
              <MaterialIcon filled>auto_awesome</MaterialIcon>
            </div>
            <div className="stitch-ai-answer">
              <span>RegIntell AI</span>
              {chatLoading ? (
                <p className="stitch-thinking">
                  <MaterialIcon>sync</MaterialIcon>
                  Thinking through the regulatory context...
                </p>
              ) : latestAssistant ? (
                <MarkdownLite content={latestAssistant.content} />
              ) : (
                <p>
                  I can summarize recent regulatory changes, explain stakeholder impact, identify deadlines, and
                  cite the source context available through the existing chat API.
                </p>
              )}
              <div className="stitch-answer-insight">
                <MaterialIcon>gavel</MaterialIcon>
                <div>
                  <h4>Context-aware regulatory answer</h4>
                  <p>
                    Responses use the current regulatory intelligence context supplied by the backend. Streaming is
                    not available from the current `/chat` contract, so loading is shown until the full reply returns.
                  </p>
                  <span>RENEWABLE PRIORITY</span>
                </div>
              </div>
              <div className="stitch-critical-card">
                <MaterialIcon>event</MaterialIcon>
                <div>
                  <span>Critical Deadline</span>
                  <strong>Ask about deadlines to surface filing windows</strong>
                </div>
                <strong>Live</strong>
              </div>
              <section className="stitch-citation-panel">
                <h4>Citations & Sources</h4>
                <div>
                  <span>1</span>
                  <p>Source references are generated only when returned in answer text.</p>
                  <MaterialIcon>download</MaterialIcon>
                </div>
                <div>
                  <span>2</span>
                  <p>Backend gap: `/chat` returns reply/model/event_id, not structured citations.</p>
                  <MaterialIcon>download</MaterialIcon>
                </div>
              </section>
              <footer className="stitch-feedback-actions">
                <button type="button"><MaterialIcon>thumb_up</MaterialIcon></button>
                <button type="button"><MaterialIcon>thumb_down</MaterialIcon></button>
                <button type="button"><MaterialIcon>content_copy</MaterialIcon></button>
                <button type="button"><MaterialIcon>sync</MaterialIcon></button>
              </footer>
            </div>
          </article>
        </main>

        <aside className="stitch-prompt-rail">
          <h3>Prompt Suggestions</h3>
          {suggestedPrompts.map((prompt) => (
            <button key={prompt} type="button" onClick={() => void handleAsk(prompt)}>
              {prompt}
            </button>
          ))}
          <h3>History</h3>
          {chatMessages.slice(-6).map((message, index) => (
            <button key={`${message.role}-${index}`} type="button" onClick={() => setChatInput(message.content)}>
              <span>{message.role === "user" ? "Question" : "Answer"}</span>
              {stripMarkdownNoise(message.content).slice(0, 84)}
            </button>
          ))}
        </aside>
      </div>

      <div className="stitch-chat-composer-wrap">
        <form
          className="stitch-chat-composer"
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
            <MaterialIcon>{chatLoading ? "sync" : "send"}</MaterialIcon>
          </button>
        </form>
      </div>
    </section>
  );
}
