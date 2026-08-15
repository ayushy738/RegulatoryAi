import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskRoute } from "./AskRoute";

vi.mock("./ask-ai/AskConversationWorkspace", () => ({
  AskConversationWorkspace: () => (
    <div data-testid="ask-conversation-workspace">Ask conversation</div>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("Ask route feature boundary", () => {
  it("renders the conversation workspace on /ask", () => {
    render(<AskRoute />);

    expect(screen.getByTestId("ask-conversation-workspace")).toBeInTheDocument();
    expect(screen.getByText("Ask conversation")).toBeInTheDocument();
  });
});
