import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskView } from "./AskView";
import { useWorkspace } from "@/app/workspace/WorkspaceContext";
import type { WorkspaceController } from "@/app/workspace/WorkspaceContext";

vi.mock("@/app/workspace/WorkspaceContext", () => ({
  useWorkspace: vi.fn(),
}));

const mockedUseWorkspace = vi.mocked(useWorkspace);

function workspace(
  overrides: Partial<WorkspaceController> = {},
): WorkspaceController {
  return {
    chatMessages: [],
    chatInput: "",
    setChatInput: vi.fn(),
    chatLoading: false,
    handleAsk: vi.fn(async () => undefined),
    chatStatus: {
      isLoading: false,
      isError: false,
      isFetching: false,
      isSuccess: true,
      error: null,
      refetch: vi.fn(),
    },
    setSelectedEvidence: vi.fn(),
    setStatusMessage: vi.fn(),
    ...overrides,
  } as unknown as WorkspaceController;
}

afterEach(() => {
  cleanup();
});

describe("legacy Ask view", () => {
  it("renders the empty state and submits an existing suggested prompt", async () => {
    const controller = workspace();
    mockedUseWorkspace.mockReturnValue(controller);
    const user = userEvent.setup();

    render(<AskView />);

    expect(screen.getByRole("heading", { name: "Ask AI" })).toBeInTheDocument();
    expect(
      screen.getByText("Start with an evidence-backed regulatory question."),
    ).toBeInTheDocument();
    expect(screen.getByText("No conversation history yet.")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "What changed this week?" }),
    );

    expect(controller.handleAsk).toHaveBeenCalledWith(
      "What changed this week?",
    );
  });

  it("renders a grounded answer and opens its structured citation", async () => {
    const setSelectedEvidence = vi.fn();
    const controller = workspace({
      chatMessages: [
        { role: "user", content: "What applies?" },
        {
          role: "assistant",
          content: "Licensed entities must comply.",
          intent: "obligation",
          model: "contract-model",
          citations: [
            {
              document_id: 17,
              title: "Electricity Rules",
              issuer: "Ministry of Power",
              issue_date: "2026-07-01",
              source_url: "https://example.test/rules",
              chunk_id: 501,
              page_number: 7,
              section_title: "Applicability",
              evidence: "The rules apply to licensed entities.",
            },
          ],
          related_questions: ["Which entities are licensed?"],
        },
      ],
      setSelectedEvidence,
    });
    mockedUseWorkspace.mockReturnValue(controller);
    const user = userEvent.setup();

    render(<AskView />);

    expect(screen.getByText("Licensed entities must comply.")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("citations in latest answer")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: /1\. Electricity Rules/i }),
    );

    expect(setSelectedEvidence).toHaveBeenCalledWith({
      title: "Electricity Rules",
      issuer: "Ministry of Power",
      date: "2026-07-01",
      evidence: "The rules apply to licensed entities.",
      sourceUrl: "https://example.test/rules",
      documentId: 17,
      chunkId: 501,
      pageNumber: 7,
      relationships: ["Section: Applicability"],
    });
  });

  it("keeps the legacy insufficient-evidence warning visible for uncited answers", () => {
    mockedUseWorkspace.mockReturnValue(
      workspace({
        chatMessages: [
          { role: "user", content: "Unknown topic" },
          {
            role: "assistant",
            content: "No evidence was found.",
            citations: [],
          },
        ],
      }),
    );

    render(<AskView />);

    expect(
      screen.getByText(/No structured citations were returned/),
    ).toBeInTheDocument();
  });

  it("wires the controlled composer and submits on Enter", () => {
    const setChatInput = vi.fn();
    const handleAsk = vi.fn(async () => undefined);
    mockedUseWorkspace.mockReturnValue(
      workspace({
        chatInput: "What deadlines apply?",
        setChatInput,
        handleAsk,
      }),
    );

    render(<AskView />);

    const composer = screen.getByPlaceholderText(
      "Ask about deadlines, obligations, consultations, amendments, or stakeholder impact",
    );
    fireEvent.change(composer, { target: { value: "Updated question" } });
    fireEvent.keyDown(composer, { key: "Enter" });

    expect(setChatInput).toHaveBeenCalledWith("Updated question");
    expect(handleAsk).toHaveBeenCalledOnce();
  });

  it("freezes the current loading state and blocks repeat submission", () => {
    const handleAsk = vi.fn(async () => undefined);
    mockedUseWorkspace.mockReturnValue(
      workspace({
        chatInput: "What deadlines apply?",
        chatLoading: true,
        handleAsk,
      }),
    );

    render(<AskView />);

    const composer = screen.getByPlaceholderText(
      "Ask about deadlines, obligations, consultations, amendments, or stakeholder impact",
    );
    fireEvent.keyDown(composer, { key: "Enter" });

    expect(handleAsk).not.toHaveBeenCalled();
    expect(
      screen.getByText("Building an evidence-backed answer..."),
    ).toBeInTheDocument();
  });
});
