import { afterEach, describe, expect, it, vi } from "vitest";

import sessionContract from "../../api/backend/tests/fixtures/ask_session_contract.json";
import {
  askSessionCreateRequestSchema,
  askSessionExportSchema,
  askSessionLifecycleActionSchema,
  askSessionListQuerySchema,
  askSessionListSchema,
  askSessionPatchRequestSchema,
  askSessionSchema,
} from "./ask-ai-sessions";
import {
  archiveAskSession,
  deleteAskSession,
  duplicateAskSession,
  exportAskSession,
  patchAskSession,
  restoreAskSession,
} from "./api";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("Ask AI session contracts", () => {
  it("parses the backend's recorded create request", () => {
    expect(
      askSessionCreateRequestSchema.parse(sessionContract.create_request),
    ).toEqual(sessionContract.create_request);
  });

  it("parses the backend's recorded session response", () => {
    expect(askSessionSchema.parse(sessionContract.session_response)).toEqual(
      sessionContract.session_response,
    );
  });

  it("parses the backend's recorded list response", () => {
    expect(askSessionListSchema.parse(sessionContract.list_response)).toEqual(
      sessionContract.list_response,
    );
  });

  it("normalizes bounded session search and filter queries", () => {
    expect(
      askSessionListQuerySchema.parse({
        cursor: "opaque",
        limit: 25,
        q: "  GRID   Code ",
        knowledge_mode: "official",
        entity: "  CERC ",
        archived: true,
        pinned: false,
      }),
    ).toEqual({
      cursor: "opaque",
      limit: 25,
      q: "grid code",
      knowledge_mode: "official",
      entity: "cerc",
      archived: true,
      pinned: false,
    });
    expect(() => askSessionListQuerySchema.parse({ q: "   " })).toThrow();
    expect(() =>
      askSessionListQuerySchema.parse({ knowledge_mode: "system" }),
    ).toThrow();
  });

  it("normalizes lifecycle patches and rejects empty changes", () => {
    expect(
      askSessionPatchRequestSchema.parse({
        title: "  Renamed research  ",
        is_pinned: true,
      }),
    ).toEqual({ title: "Renamed research", is_pinned: true });
    expect(() => askSessionPatchRequestSchema.parse({})).toThrow();
    expect(
      askSessionLifecycleActionSchema.parse({
        type: "archive",
        session_id: sessionContract.session_response.id,
      }),
    ).toEqual({
      type: "archive",
      session_id: sessionContract.session_response.id,
    });
    expect(() =>
      askSessionLifecycleActionSchema.parse({
        type: "delete",
        session_id: "not-a-session",
      }),
    ).toThrow();
  });

  it("parses the safe versioned export shape", () => {
    expect(
      askSessionExportSchema.parse({
        schema_version: "1",
        session: sessionContract.session_response,
        turns: [],
        saved_items: [],
      }),
    ).toEqual({
      schema_version: "1",
      session: sessionContract.session_response,
      turns: [],
      saved_items: [],
    });
  });

  it("uses the exact lifecycle/export endpoints and handles deletion without JSON", async () => {
    const exportPayload = {
      schema_version: "1",
      session: sessionContract.session_response,
      turns: [],
      saved_items: [],
    };
    const fetchMock = vi.fn(
      async (input: RequestInfo | URL, init?: RequestInit) => {
        const path = String(input);
        if (init?.method === "DELETE") {
          return new Response(null, { status: 204 });
        }
        return new Response(
          JSON.stringify(
            path.endsWith("/export")
              ? exportPayload
              : sessionContract.session_response,
          ),
          {
            status:
              path.endsWith("/duplicate") ? 201 : 200,
            headers: { "Content-Type": "application/json" },
          },
        );
      },
    );
    vi.stubGlobal("fetch", fetchMock);
    const sessionId = sessionContract.session_response.id;
    const token = "explicit-session-token";

    await patchAskSession(sessionId, { title: " Renamed " }, token);
    await archiveAskSession(sessionId, token);
    await restoreAskSession(sessionId, token);
    await duplicateAskSession(sessionId, token);
    await exportAskSession(sessionId, token);
    await deleteAskSession(sessionId, token);

    const calls = fetchMock.mock.calls.map(([input, init]) => ({
      path: String(input),
      method: init?.method,
      body: init?.body,
      authorization: new Headers(init?.headers).get("Authorization"),
    }));
    expect(calls.map(({ path }) => new URL(path).pathname)).toEqual([
      `/chat/sessions/${sessionId}`,
      `/chat/sessions/${sessionId}/archive`,
      `/chat/sessions/${sessionId}/restore`,
      `/chat/sessions/${sessionId}/duplicate`,
      `/chat/sessions/${sessionId}/export`,
      `/chat/sessions/${sessionId}`,
    ]);
    expect(calls.map(({ method }) => method)).toEqual([
      "PATCH",
      "POST",
      "POST",
      "POST",
      undefined,
      "DELETE",
    ]);
    expect(calls[0]?.body).toBe(JSON.stringify({ title: "Renamed" }));
    expect(
      calls.every(({ authorization }) => authorization === `Bearer ${token}`),
    ).toBe(true);
  });
});
