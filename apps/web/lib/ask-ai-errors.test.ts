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

  it("extracts FastAPI detail strings when no Ask AI code exists", () => {
    expect(
      parseAskErrorResponse('{"detail":"Source page already exists"}', "header-request"),
    ).toEqual({
      message: "Source page already exists",
      code: undefined,
      correlationId: "header-request",
    });
  });

  it("extracts message from structured FastAPI detail objects", () => {
    expect(
      parseAskErrorResponse(
        JSON.stringify({
          detail: {
            message: "A removed page with this URL already exists; restore it instead.",
            page_id: 84,
            retired: true,
            hint: "restore",
          },
        }),
        "header-request",
      ),
    ).toEqual({
      message: "A removed page with this URL already exists; restore it instead.",
      code: undefined,
      correlationId: "header-request",
    });
  });

  it("preserves the legacy raw-body fallback when JSON has no detail string", () => {
    expect(parseAskErrorResponse("legacy failure", "header-request")).toEqual({
      message: "legacy failure",
      code: undefined,
      correlationId: "header-request",
    });
  });
});
