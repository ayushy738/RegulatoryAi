"use client";

import { Menu, PanelRight, Send, X } from "lucide-react";
import {
  useEffect,
  useId,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent as ReactKeyboardEvent,
  type ReactNode,
} from "react";

const MAX_RESEARCH_QUESTION_LENGTH = 10_000;

export type ResearchSubmission = Readonly<{
  question: string;
}>;

export type ResearchSubmitCapability = (
  submission: ResearchSubmission,
) => Promise<void> | void;

type SubmissionState = "idle" | "submitting" | "submitted" | "failed";

export function ResearchWorkspaceShell({
  onSubmit,
  navigationContent,
  canvasContent,
  evidenceContent,
  onNewResearch,
  onDraftChange,
  composerSuggestions,
  onComposerKeyDown,
}: {
  onSubmit?: ResearchSubmitCapability;
  navigationContent?: ReactNode;
  canvasContent?: ReactNode;
  evidenceContent?: ReactNode;
  onNewResearch?: () => void;
  onDraftChange?: (draft: string) => void;
  composerSuggestions?: ReactNode;
  onComposerKeyDown?: (
    event: ReactKeyboardEvent<HTMLTextAreaElement>,
  ) => boolean;
}) {
  const generatedId = useId().replaceAll(":", "");
  const navigationId = `research-navigation-${generatedId}`;
  const evidenceId = `research-evidence-${generatedId}`;
  const composerId = `research-composer-${generatedId}`;
  const navigationCloseRef = useRef<HTMLButtonElement | null>(null);
  const evidenceCloseRef = useRef<HTMLButtonElement | null>(null);
  const composerRef = useRef<HTMLTextAreaElement | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  const [evidenceOpen, setEvidenceOpen] = useState(false);
  const [draft, setDraft] = useState("");
  const [submissionState, setSubmissionState] =
    useState<SubmissionState>("idle");

  useEffect(() => {
    if (navigationOpen) navigationCloseRef.current?.focus();
  }, [navigationOpen]);

  useEffect(() => {
    if (evidenceOpen) evidenceCloseRef.current?.focus();
  }, [evidenceOpen]);

  useEffect(() => {
    function closePanels(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setNavigationOpen(false);
        setEvidenceOpen(false);
      }
    }
    document.addEventListener("keydown", closePanels);
    return () => document.removeEventListener("keydown", closePanels);
  }, []);

  function openNavigation() {
    setEvidenceOpen(false);
    setNavigationOpen(true);
  }

  function openEvidence() {
    setNavigationOpen(false);
    setEvidenceOpen(true);
  }

  async function submitResearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const question = draft.trim();
    if (
      onSubmit === undefined ||
      submissionState === "submitting" ||
      !question
    ) {
      return;
    }
    const submittedDraft = draft;
    setSubmissionState("submitting");
    try {
      await onSubmit({ question });
      setDraft((current) => (current === submittedDraft ? "" : current));
      setSubmissionState("submitted");
    } catch {
      setSubmissionState("failed");
    }
  }

  const submitEnabled =
    onSubmit !== undefined &&
    submissionState !== "submitting" &&
    draft.trim().length > 0;
  const panelOpen = navigationOpen || evidenceOpen;

  return (
    <div className="research-workspace-shell">
      <div className="research-workspace-mobile-controls">
        <button
          type="button"
          aria-expanded={navigationOpen}
          aria-controls={navigationId}
          onClick={openNavigation}
        >
          <Menu size={17} aria-hidden="true" />
          Research navigation
        </button>
        <button
          type="button"
          aria-expanded={evidenceOpen}
          aria-controls={evidenceId}
          onClick={openEvidence}
        >
          <PanelRight size={17} aria-hidden="true" />
          Evidence
        </button>
      </div>

      {panelOpen ? (
        <button
          type="button"
          className="research-workspace-backdrop"
          aria-label="Close research panels"
          onClick={() => {
            setNavigationOpen(false);
            setEvidenceOpen(false);
          }}
        />
      ) : null}

      <aside
        id={navigationId}
        className="research-workspace-navigation"
        data-open={navigationOpen ? "true" : "false"}
        aria-label="Research navigation"
      >
        <div className="research-workspace-panel-heading">
          <div>
            <p>Regulatory intelligence</p>
            <h2>Research</h2>
          </div>
          <button
            ref={navigationCloseRef}
            type="button"
            className="research-workspace-panel-close"
            aria-label="Close research navigation"
            onClick={() => setNavigationOpen(false)}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <a
          className="research-workspace-new-link"
          href={`#${composerId}`}
          onClick={() => {
            setNavigationOpen(false);
            onNewResearch?.();
            composerRef.current?.focus();
          }}
        >
          New Research
        </a>
        {navigationContent ?? (
          <div className="research-workspace-placeholder">
            <section aria-labelledby={`${navigationId}-recent`}>
              <h3 id={`${navigationId}-recent`}>Recent Research</h3>
              <p>Your recent research will appear here.</p>
            </section>
            <section aria-labelledby={`${navigationId}-pinned`}>
              <h3 id={`${navigationId}-pinned`}>Pinned</h3>
              <p>Pinned research will appear here.</p>
            </section>
          </div>
        )}
      </aside>

      <section
        className="research-workspace-canvas"
        aria-labelledby={`${composerId}-title`}
      >
        <header className="research-workspace-canvas-heading">
          <p>Regulatory Intelligence Workspace</p>
          <h1 id={`${composerId}-title`}>Research</h1>
          <span>
            Ask a question, inspect the evidence, and continue in one workspace.
          </span>
        </header>

        <form
          className="research-workspace-composer"
          onSubmit={(event) => void submitResearch(event)}
          aria-label="Start regulatory research"
        >
          <label htmlFor={composerId}>Ask a regulatory research question</label>
          <div>
            <textarea
              ref={composerRef}
              id={composerId}
              value={draft}
              maxLength={MAX_RESEARCH_QUESTION_LENGTH}
              rows={3}
              placeholder="Ask about regulations, obligations, deadlines, amendments, or current developments"
              onChange={(event) => {
                setDraft(event.target.value);
                onDraftChange?.(event.target.value);
                if (
                  submissionState === "submitted" ||
                  submissionState === "failed"
                ) {
                  setSubmissionState("idle");
                }
              }}
              onKeyDown={(event) => {
                if (onComposerKeyDown?.(event)) {
                  return;
                }
                if (
                  event.key === "Enter" &&
                  !event.shiftKey &&
                  submitEnabled
                ) {
                  event.preventDefault();
                  event.currentTarget.form?.requestSubmit();
                }
              }}
            />
            <button type="submit" disabled={!submitEnabled}>
              <Send size={17} aria-hidden="true" />
              {submissionState === "submitting"
                ? "Starting research"
                : "Start research"}
            </button>
          </div>
          {composerSuggestions}
          <p className="research-workspace-submit-status" role="status">
            {onSubmit === undefined
              ? "Research submission is not enabled in this rollout."
              : submissionState === "submitting"
                ? "Starting research…"
                : submissionState === "submitted"
                  ? "Research request submitted."
                  : submissionState === "failed"
                    ? "Research could not be submitted. Your draft is preserved."
                    : "Press Enter to submit or Shift+Enter for a new line."}
          </p>
        </form>

        <section
          className="research-workspace-results"
          aria-label="Research results"
        >
          {canvasContent ?? (
            <div className="research-workspace-empty-canvas" role="status">
              <h2>Start with a regulatory question</h2>
              <p>
                Structured results will appear here as evidence becomes
                available.
              </p>
            </div>
          )}
        </section>
      </section>

      <aside
        id={evidenceId}
        className="research-workspace-evidence"
        data-open={evidenceOpen ? "true" : "false"}
        aria-label="Evidence panel"
      >
        <div className="research-workspace-panel-heading">
          <div>
            <p>Inspect without leaving context</p>
            <h2>Evidence</h2>
          </div>
          <button
            ref={evidenceCloseRef}
            type="button"
            className="research-workspace-panel-close"
            aria-label="Close evidence panel"
            onClick={() => setEvidenceOpen(false)}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {evidenceContent ?? (
          <div className="research-workspace-empty-evidence" role="status">
            <h3>No evidence selected</h3>
            <p>
              Select verified evidence from a research result to inspect its
              source, status, locator, and excerpt.
            </p>
          </div>
        )}
      </aside>
    </div>
  );
}
