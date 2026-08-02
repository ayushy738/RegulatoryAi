import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AskRoute } from "./AskRoute";

vi.mock("@/lib/ask-ai-data", () => ({
  ResearchWorkspaceDataProvider: ({
    children,
    enabled,
  }: {
    children: React.ReactNode;
    enabled: boolean;
  }) => (
    <div data-testid="research-data-provider" data-enabled={String(enabled)}>
      {children}
    </div>
  ),
}));

vi.mock("./ask-ai/ResearchWorkspace", () => ({
  ResearchWorkspace: ({
    onSubmit,
  }: {
    onSubmit?: (value: { question: string }) => void;
  }) => (
    <button
      type="button"
      onClick={() => onSubmit?.({ question: "route research" })}
    >
      registered-v2-research-shell
    </button>
  ),
}));

afterEach(() => {
  cleanup();
});

describe("Ask route feature boundary", () => {
  it("always registers the Research Workspace on the Ask route", () => {
    render(<AskRoute />);

    expect(
      screen.getByRole("button", { name: "registered-v2-research-shell" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("research-data-provider")).toHaveAttribute(
      "data-enabled",
      "true",
    );
  });

  it("passes only an explicit submit capability into the registered shell", async () => {
    const user = userEvent.setup();
    const onResearchSubmit = vi.fn();
    render(<AskRoute onResearchSubmit={onResearchSubmit} />);

    await user.click(
      screen.getByRole("button", {
        name: "registered-v2-research-shell",
      }),
    );
    expect(onResearchSubmit).toHaveBeenCalledWith({
      question: "route research",
    });
  });
});
