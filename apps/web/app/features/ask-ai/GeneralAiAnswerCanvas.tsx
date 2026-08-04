"use client";

import { useId } from "react";

import type { AskGeneralAiAnswer } from "@/lib/ask-ai-data";

import {
  KnowledgeModeSection,
  ModeStatePanel,
  NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
  OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
} from "./ModePrimitives";

// The section banner renders the frozen disclosure, so the answer body must not
// repeat the copy the backend already appended.
function answerBlocks(reply: string) {
  return reply
    .split(/\n{2,}/)
    .map((block) => block.trim())
    .filter(
      (block) =>
        block.length > 0 &&
        block !== NO_OFFICIAL_DOCUMENTS_DISCLOSURE &&
        block !== OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
    );
}

export function GeneralAiAnswerCanvas({
  mention,
  answer,
  pending = false,
  error = null,
}: {
  mention: string;
  answer: AskGeneralAiAnswer | null;
  pending?: boolean;
  error?: string | null;
}) {
  const generatedId = useId().replaceAll(":", "");
  if (pending) {
    return (
      <div className="research-workspace-empty-canvas" role="status">
        <h2>No canonical entity matched “{mention}”</h2>
        <p>Preparing a general AI explanation…</p>
      </div>
    );
  }
  if (answer === null || error !== null) {
    return <ModeStatePanel kind="general_ai_unavailable" manualSearchHref="/browse" />;
  }
  return (
    <div className="entity-intelligence-page">
      <KnowledgeModeSection
        banner={{
          id: `general-ai-answer-${generatedId}`,
          mode: "general_ai",
          confidence: "Medium",
          trigger: "healthy_official_no_match",
        }}
        manualSearchHref="/browse"
      >
        {answerBlocks(answer.reply).map((block) => (
          <p key={block}>{block}</p>
        ))}
      </KnowledgeModeSection>
    </div>
  );
}
