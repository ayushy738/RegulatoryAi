import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AskConversationWorkspace } from "./AskConversationWorkspace";

const sendChat = vi.fn();
const listChatConversations = vi.fn();
const getChatConversation = vi.fn();

vi.mock("@/app/workspace/WorkspaceContext", () => ({
  useWorkspace: () => ({ token: "test-token" }),
}));

vi.mock("@/lib/api", () => ({
  sendChat: (...args: unknown[]) => sendChat(...args),
  listChatConversations: (...args: unknown[]) => listChatConversations(...args),
  getChatConversation: (...args: unknown[]) => getChatConversation(...args),
}));

const OFFICIAL_CITATION = {
  document_id: 1,
  title: "DSM Framework",
  issuer: "KERC",
  issue_date: "2026-03-10",
  source_url: "https://example.gov.in/dsm",
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

beforeEach(() => {
  listChatConversations.mockResolvedValue([]);
  window.history.replaceState({}, "", "/ask");
});

describe("AskConversationWorkspace", () => {
  it("keeps a clean empty state and does not submit while typing", async () => {
    const user = userEvent.setup();
    render(<AskConversationWorkspace />);

    expect(
      await screen.findByRole("heading", { level: 1, name: "Regulatory AI" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("What can I help you research?"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Start research/i)).not.toBeInTheDocument();

    const composer = screen.getByLabelText(
      "Ask anything about Indian regulation",
    );
    await user.type(composer, "DSM");

    await waitFor(() => {
      expect(sendChat).not.toHaveBeenCalled();
    });
    expect(composer).toHaveValue("DSM");
  });

  it("submits once on Enter and never on Shift+Enter", async () => {
    const user = userEvent.setup();
    sendChat.mockResolvedValue({
      reply: "DSM is Demand Side Management.",
      model: "test",
      event_id: null,
      session_id: "session-1",
      knowledge_basis: "official",
      citations: [OFFICIAL_CITATION],
      related_questions: [],
    });

    render(<AskConversationWorkspace />);
    const composer = await screen.findByLabelText(
      "Ask anything about Indian regulation",
    );

    await user.type(
      composer,
      "What is DSM?{Shift>}{Enter}{/Shift}Follow-up line",
    );
    expect(sendChat).not.toHaveBeenCalled();
    expect(composer).toHaveValue("What is DSM?\nFollow-up line");

    await user.clear(composer);
    await user.type(composer, "What is DSM in India?{Enter}");

    await waitFor(() => {
      expect(sendChat).toHaveBeenCalledTimes(1);
    });
    expect(sendChat).toHaveBeenCalledWith(
      "What is DSM in India?",
      null,
      "test-token",
      null,
    );
    expect(
      await screen.findByText("DSM is Demand Side Management."),
    ).toBeInTheDocument();
    expect(screen.getByText("DSM Framework")).toBeInTheDocument();
  });

  it("restores a conversation from history without regenerating", async () => {
    const user = userEvent.setup();
    listChatConversations.mockResolvedValue([
      {
        id: "session-1",
        title: "DSM in India",
        updated_at: new Date().toISOString(),
      },
    ]);
    getChatConversation.mockResolvedValue({
      id: "session-1",
      messages: [
        {
          id: 1,
          role: "user",
          content: "What is DSM in India?",
          citations: [],
        },
        {
          id: 2,
          role: "assistant",
          content: "Persisted answer",
          knowledge_basis: "official",
          citations: [OFFICIAL_CITATION],
        },
      ],
    });

    render(<AskConversationWorkspace />);
    await user.click(
      await screen.findByRole("button", { name: "DSM in India" }),
    );

    expect(await screen.findByText("Persisted answer")).toBeInTheDocument();
    expect(sendChat).not.toHaveBeenCalled();
    expect(getChatConversation).toHaveBeenCalledWith("session-1", "test-token");
  });

  it("renders each restored answer with its own citations", async () => {
    const user = userEvent.setup();
    listChatConversations.mockResolvedValue([
      { id: "session-a", title: "Chat A", updated_at: "2026-08-15T10:00:00Z" },
      { id: "session-b", title: "Chat B", updated_at: "2026-08-15T09:00:00Z" },
    ]);
    getChatConversation.mockImplementation(async (id: string) =>
      id === "session-a"
        ? {
            id: "session-a",
            messages: [
              { id: 1, role: "user", content: "What is DSM?", citations: [] },
              {
                id: 2,
                role: "assistant",
                content: "Answer A",
                knowledge_basis: "official",
                citations: [{ ...OFFICIAL_CITATION, title: "Sources A" }],
              },
            ],
          }
        : {
            id: "session-b",
            messages: [
              { id: 3, role: "user", content: "What is DSM?", citations: [] },
              {
                id: 4,
                role: "assistant",
                content: "Answer B",
                knowledge_basis: "official",
                citations: [{ ...OFFICIAL_CITATION, title: "Sources B" }],
              },
            ],
          },
    );

    render(<AskConversationWorkspace />);

    await user.click(await screen.findByRole("button", { name: "Chat A" }));
    expect(await screen.findByText("Answer A")).toBeInTheDocument();
    expect(screen.getByText("Sources A")).toBeInTheDocument();
    expect(screen.queryByText("Sources B")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Chat B" }));
    expect(await screen.findByText("Answer B")).toBeInTheDocument();
    expect(screen.getByText("Sources B")).toBeInTheDocument();
    expect(screen.queryByText("Sources A")).not.toBeInTheDocument();
    expect(sendChat).not.toHaveBeenCalled();
  });

  it("restores the persisted knowledge basis instead of inferring it", async () => {
    listChatConversations.mockResolvedValue([]);
    getChatConversation.mockResolvedValue({
      id: "session-general",
      messages: [
        { id: 1, role: "user", content: "What is DSM?", citations: [] },
        {
          id: 2,
          role: "assistant",
          content: "General explanation",
          knowledge_basis: "general",
          citations: [],
        },
      ],
    });
    window.history.replaceState({}, "", "/ask?session=session-general");

    render(<AskConversationWorkspace />);

    expect(await screen.findByText("General explanation")).toBeInTheDocument();
    expect(
      screen.getByText(/General knowledge explanation/),
    ).toBeInTheDocument();
    expect(sendChat).not.toHaveBeenCalled();
  });
});
