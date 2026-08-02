import { describe, expect, it } from "vitest";

import {
  isAskErrorCode,
  parseAskErrorResponse,
  safeAskErrorMessage,
} from "./ask-ai-errors";

describe("Ask AI safe errors", () => {
  it("maps stable product codes to actionable copy", () => {
    expect(safeAskErrorMessage("MODEL_UNAVAILABLE")).toBe(
      "The AI service is temporarily unavailable.",
    );
    expect(safeAskErrorMessage("RETRIEVAL_UNAVAILABLE")).not.toMatch(
      /http|sql|provider|stack/i,
    );
  });

  it("rejects unknown codes so legacy errors retain their fallback path", () => {
    expect(isAskErrorCode("MODEL_UNAVAILABLE")).toBe(true);
    expect(isAskErrorCode("HTTP 503 provider detail")).toBe(false);
    expect(isAskErrorCode(undefined)).toBe(false);
  });

  it("uses safe code copy instead of a raw structured detail", () => {
    expect(
      parseAskErrorResponse(
        JSON.stringify({
          detail: "HTTP 503 from provider-internal.example",
          code: "MODEL_UNAVAILABLE",
          correlation_id: "request-123",
        }),
      ),
    ).toEqual({
      message: "The AI service is temporarily unavailable.",
      code: "MODEL_UNAVAILABLE",
      correlationId: "request-123",
    });
  });

  it("preserves the legacy raw-body fallback when no stable code exists", () => {
    expect(
      parseAskErrorResponse('{"detail":"legacy failure"}', "header-request"),
    ).toEqual({
      message: '{"detail":"legacy failure"}',
      code: undefined,
      correlationId: "header-request",
    });
  });
});
