import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ResearchWorkspaceShell } from "./ResearchWorkspaceShell";

afterEach(() => {
  cleanup();
});

describe("Ask AI Research Workspace shell", () => {
  it("renders the semantic three-pane workspace and immediate composer", () => {
    render(<ResearchWorkspaceShell />);

    expect(
      screen.getByRole("complementary", { name: "Research navigation" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("region", { name: "Research" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("complementary", { name: "Evidence panel" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { level: 1, name: "Research" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("textbox", {
        name: "Ask a regulatory research question",
      }),
    ).toBeEnabled();
    expect(
      screen.getByRole("button", { name: "Start research" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Research submission is not enabled in this rollout.",
      ),
    ).toBeInTheDocument();
  });

  it("keeps an editable draft across safe shell rerenders", async () => {
    const user = userEvent.setup();
    const rendered = render(<ResearchWorkspaceShell />);
    const composer = screen.getByRole("textbox", {
      name: "Ask a regulatory research question",
    });

    await user.type(composer, "What is DSM?");
    rendered.rerender(<ResearchWorkspaceShell />);

    expect(composer).toHaveValue("What is DSM?");
    expect(
      screen.getByRole("button", { name: "Start research" }),
    ).toBeDisabled();
  });

  it("submits a trimmed question by keyboard and clears only after acknowledgement", async () => {
    const user = userEvent.setup();
    let acknowledge: (() => void) | undefined;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          acknowledge = resolve;
        }),
    );
    render(<ResearchWorkspaceShell onSubmit={onSubmit} />);
    const composer = screen.getByRole("textbox", {
      name: "Ask a regulatory research question",
    });

    await user.type(composer, "  Latest DSM  ");
    await user.keyboard("{Enter}");

    expect(onSubmit).toHaveBeenCalledWith({ question: "Latest DSM" });
    expect(composer).toHaveValue("  Latest DSM  ");
    expect(
      screen.getByRole("button", { name: "Starting research" }),
    ).toBeDisabled();
    expect(screen.getByText("Starting research…")).toBeInTheDocument();

    await act(async () => {
      acknowledge?.();
    });
    await waitFor(() => expect(composer).toHaveValue(""));
    expect(
      screen.getByText("Research request submitted."),
    ).toBeInTheDocument();
  });

  it("preserves the draft and exposes only safe copy when submission fails", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => {
      throw new Error("provider secret detail");
    });
    render(<ResearchWorkspaceShell onSubmit={onSubmit} />);
    const composer = screen.getByRole("textbox", {
      name: "Ask a regulatory research question",
    });

    await user.type(composer, "Compare DSM and ABT");
    await user.click(screen.getByRole("button", { name: "Start research" }));

    expect(
      await screen.findByText(
        "Research could not be submitted. Your draft is preserved.",
      ),
    ).toBeInTheDocument();
    expect(composer).toHaveValue("Compare DSM and ABT");
    expect(screen.queryByText("provider secret detail")).not.toBeInTheDocument();
  });

  it("does not clear a newer draft when an earlier submission completes", async () => {
    const user = userEvent.setup();
    let acknowledge: (() => void) | undefined;
    const onSubmit = vi.fn(
      () =>
        new Promise<void>((resolve) => {
          acknowledge = resolve;
        }),
    );
    render(<ResearchWorkspaceShell onSubmit={onSubmit} />);
    const composer = screen.getByRole("textbox", {
      name: "Ask a regulatory research question",
    });

    await user.type(composer, "First research");
    await user.click(screen.getByRole("button", { name: "Start research" }));
    await user.type(composer, " plus a new draft");
    await act(async () => {
      acknowledge?.();
    });

    await waitFor(() =>
      expect(composer).toHaveValue("First research plus a new draft"),
    );
  });

  it("uses Shift+Enter for a new line without submitting", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<ResearchWorkspaceShell onSubmit={onSubmit} />);
    const composer = screen.getByRole("textbox", {
      name: "Ask a regulatory research question",
    });

    await user.type(composer, "DSM");
    await user.keyboard("{Shift>}{Enter}{/Shift}timeline");

    expect(onSubmit).not.toHaveBeenCalled();
    expect(composer).toHaveValue("DSM\ntimeline");
  });

  it("opens one responsive panel at a time and closes it with Escape", async () => {
    const user = userEvent.setup();
    render(<ResearchWorkspaceShell />);
    const navigationButton = screen.getByRole("button", {
      name: "Research navigation",
    });
    const evidenceButton = screen.getByRole("button", { name: "Evidence" });
    const navigation = screen.getByRole("complementary", {
      name: "Research navigation",
    });
    const evidence = screen.getByRole("complementary", {
      name: "Evidence panel",
    });

    await user.click(navigationButton);
    expect(navigationButton).toHaveAttribute("aria-expanded", "true");
    expect(navigation).toHaveAttribute("data-open", "true");
    expect(
      screen.getByRole("button", { name: "Close research navigation" }),
    ).toHaveFocus();

    await user.click(evidenceButton);
    expect(navigation).toHaveAttribute("data-open", "false");
    expect(evidence).toHaveAttribute("data-open", "true");

    await user.keyboard("{Escape}");
    expect(evidenceButton).toHaveAttribute("aria-expanded", "false");
    expect(evidence).toHaveAttribute("data-open", "false");
  });

  it("moves New Research directly to the composer", async () => {
    const user = userEvent.setup();
    const onNewResearch = vi.fn();
    render(<ResearchWorkspaceShell onNewResearch={onNewResearch} />);

    await user.click(screen.getByRole("link", { name: "New Research" }));

    expect(
      screen.getByRole("textbox", {
        name: "Ask a regulatory research question",
      }),
    ).toHaveFocus();
    expect(onNewResearch).toHaveBeenCalledTimes(1);
  });

  it("accepts real future region content without adding cosmetic shell actions", () => {
    render(
      <ResearchWorkspaceShell
        navigationContent={<div>Owned session navigation</div>}
        canvasContent={<article>Stored structured result</article>}
        evidenceContent={<article>Selected official evidence</article>}
      />,
    );

    expect(screen.getByText("Owned session navigation")).toBeInTheDocument();
    expect(screen.getByText("Stored structured result")).toBeInTheDocument();
    expect(screen.getByText("Selected official evidence")).toBeInTheDocument();
    expect(
      screen.queryByText("Your recent research will appear here."),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("No evidence selected"),
    ).not.toBeInTheDocument();
    const navigation = screen.getByRole("complementary", {
      name: "Research navigation",
    });
    expect(
      within(navigation).queryByRole("button", { name: /archive|rename|pin/i }),
    ).not.toBeInTheDocument();
  });
});
