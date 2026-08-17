export const askErrorMessages = {
  AUTH_REQUIRED: "Sign in to continue using Ask AI.",
  RATE_LIMITED: "Too many Ask AI requests. Please wait and try again.",
  INVALID_QUESTION: "Enter a valid regulatory question and try again.",
  AMBIGUOUS_SCOPE: "Add a jurisdiction or regulatory scope and try again.",
  RETRIEVAL_DEGRADED: "Some regulatory evidence is temporarily unavailable.",
  RETRIEVAL_UNAVAILABLE: "Regulatory evidence retrieval is temporarily unavailable.",
  NO_GROUNDED_EVIDENCE: "No citation-backed regulatory evidence was found.",
  MODEL_REJECTED_REQUEST: "The AI service could not process this question.",
  MODEL_UNAVAILABLE: "The AI service is temporarily unavailable.",
  CITATION_VERIFICATION_FAILED: "The answer could not be verified against its citations.",
  PERSISTENCE_FAILED: "The research result could not be saved.",
  RUN_CANCELLED: "The Ask AI request was cancelled.",
} as const;

export type AskErrorCode = keyof typeof askErrorMessages;

export function isAskErrorCode(value: unknown): value is AskErrorCode {
  return typeof value === "string" && value in askErrorMessages;
}

export function safeAskErrorMessage(code: AskErrorCode): string {
  return askErrorMessages[code];
}

export function parseAskErrorResponse(
  detail: string,
  headerCorrelationId?: string,
): {
  message: string;
  code?: AskErrorCode;
  correlationId?: string;
} {
  let payload: Record<string, unknown> | undefined;
  try {
    const parsed: unknown = JSON.parse(detail);
    payload =
      parsed !== null && typeof parsed === "object"
        ? (parsed as Record<string, unknown>)
        : undefined;
  } catch {
    payload = undefined;
  }
  const code = isAskErrorCode(payload?.code) ? payload.code : undefined;
  const correlationId =
    typeof payload?.correlation_id === "string"
      ? payload.correlation_id
      : headerCorrelationId;
  const detailValue = payload?.detail;
  const fastapiDetail =
    typeof detailValue === "string"
      ? detailValue
      : detailValue !== null &&
          typeof detailValue === "object" &&
          typeof (detailValue as { message?: unknown }).message === "string"
        ? (detailValue as { message: string }).message
        : undefined;
  return {
    message: code ? safeAskErrorMessage(code) : fastapiDetail || detail,
    code,
    correlationId,
  };
}
