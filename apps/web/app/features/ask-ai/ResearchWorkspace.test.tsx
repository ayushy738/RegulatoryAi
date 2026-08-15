import {
  act,
  cleanup,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { entityCorePageFixture } from "../../../test/entity-core-page-fixture";
import { federatedSearchFixture } from "../../../test/federated-search-fixture";
import responseContract from "../../../../api/backend/tests/fixtures/ask_response_contract.json";

import { ResearchWorkspace } from "./ResearchWorkspace";

const lookupFixture = vi.hoisted(() => ({
  state: {
    enabled: true,
    available: true,
    isPending: false,
    mutateAsync: vi.fn(),
    searchAvailable: false,
    searchPending: false,
    searchAsync: vi.fn(),
    generalAvailable: false,
    generalPending: false,
    generalAsync: vi.fn(),
  },
}));

vi.mock("@/lib/ask-ai-data", () => ({
  useResearchWorkspaceScope: () => ({
    enabled: lookupFixture.state.enabled,
  }),
  useResolveResearchEntity: () => ({
    available: lookupFixture.state.available,
    isPending: lookupFixture.state.isPending,
    mutateAsync: lookupFixture.state.mutateAsync,
  }),
  useFederatedResearchSearch: () => ({
    available: lookupFixture.state.searchAvailable,
    isPending: lookupFixture.state.searchPending,
    mutateAsync: lookupFixture.state.searchAsync,
  }),
  useGeneralAiAnswer: () => ({
    available: lookupFixture.state.generalAvailable,
    isPending: lookupFixture.state.generalPending,
    mutateAsync: lookupFixture.state.generalAsync,
  }),
}));

vi.mock("./ResearchSessionRail", () => ({
  ResearchSessionRail: ({
    activeSessionId,
  }: {
    activeSessionId: string | null;
  }) => <nav>Session rail: {activeSessionId ?? "none"}</nav>,
}));

const dsm = {
  canonical_id: "in.central.dsm",
  canonical_name: "Deviation Settlement Mechanism",
  entity_class: "regulatory_concept",
  jurisdiction: "India/Central",
  aliases: ["DSM", "Deviation Settlement"],
  confidence: 0.95,
  assumed: false,
  match_reason: "Matched an approved alias.",
  entity_route: "/ask?entity=in.central.dsm",
} as const;

const resolvedDsm = {
  schema_version: "1",
  policy_version: "ask-ai-decision-v1",
  status: "resolved",
  mention: "DSM",
  match_rule: "exact_alias",
  selected: dsm,
  candidates: [],
  clarification_question: null,
  surface: "entity_intelligence_page",
} as const;

beforeEach(() => {
  lookupFixture.state.enabled = true;
  lookupFixture.state.available = true;
  lookupFixture.state.isPending = false;
  lookupFixture.state.mutateAsync.mockReset();
  lookupFixture.state.searchAvailable = false;
  lookupFixture.state.searchPending = false;
  lookupFixture.state.searchAsync.mockReset();
  lookupFixture.state.generalAvailable = false;
  lookupFixture.state.generalPending = false;
  lookupFixture.state.generalAsync.mockReset();
  window.history.replaceState({}, "", "/ask");
});

afterEach(() => {
  cleanup();
});

describe("Research Workspace entity lookup route", () => {
  it("mounts an injected structured response in the center canvas", () => {
    render(
      <ResearchWorkspace
        onSubmit={vi.fn()}
        structuredResponse={responseContract}
      />,
    );

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /The filing obligation is in force/,
      }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Official findings" }))
      .toBeInTheDocument();
  });

  it("opens bare DSM as an Entity Intelligence Page with visible expansion", async () => {
    const user = userEvent.setup();
    lookupFixture.state.mutateAsync.mockResolvedValue(resolvedDsm);
    render(
      <ResearchWorkspace
        entityCorePage={{
          ...entityCorePageFixture(),
          canonical_id: dsm.canonical_id,
        }}
      />,
    );

    await user.type(
      screen.getByLabelText("Ask a regulatory research question"),
      "DSM",
    );
    await user.keyboard("{Enter}");

    expect(lookupFixture.state.mutateAsync).toHaveBeenCalledWith({
      mention: "DSM",
    });
    expect(
      await screen.findByRole("heading", {
        name: "Deviation Settlement Mechanism",
      }),
    ).toBeInTheDocument();
    expect(document.querySelector(".entity-expansion")).toHaveTextContent(
      "DSM maps to Deviation Settlement Mechanism.",
    );
    expect(
      screen.getByText("Entity Intelligence Page"),
    ).toBeInTheDocument();
    expect(
      document.querySelector(
        '[data-surface="entity_intelligence_page"]',
      ),
    ).not.toBeNull();
    expect(
      screen.getByRole("region", { name: "Overview" }),
    ).toHaveAttribute("data-mode", "grounded_regulatory");
    expect(
      screen.getByRole("region", { name: "Official Documents" }),
    ).toBeInTheDocument();
    expect(window.location.pathname + window.location.search).toBe(
      "/ask?entity=in.central.dsm",
    );
  });

  it("requires an explicit keyboard choice and re-resolves canonical identity", async () => {
    const user = userEvent.setup();
    const beta = {
      ...dsm,
      canonical_id: "test.arc-beta",
      canonical_name: "Alternate Reliability Charge",
      aliases: ["ARC"],
      confidence: 0.49,
      entity_route: "/ask?entity=test.arc-beta",
    } as const;
    lookupFixture.state.mutateAsync
      .mockResolvedValueOnce({
        ...resolvedDsm,
        status: "ambiguous",
        mention: "ARC",
        match_rule: "clarification",
        selected: null,
        candidates: [
          {
            ...dsm,
            canonical_id: "test.arc-alpha",
            canonical_name: "Alpha Regulatory Code",
            aliases: ["ARC"],
            confidence: 0.49,
            entity_route: "/ask?entity=test.arc-alpha",
          },
          beta,
        ],
        clarification_question:
          "Which did you mean by 'ARC': Alpha Regulatory Code or Alternate Reliability Charge?",
        surface: null,
      })
      .mockResolvedValueOnce({
        ...resolvedDsm,
        mention: "test.arc-beta",
        match_rule: "exact_canonical",
        selected: {
          ...beta,
          confidence: 1,
          match_reason: "Matched the canonical entity.",
        },
      });
    render(<ResearchWorkspace />);

    await user.type(
      screen.getByLabelText("Ask a regulatory research question"),
      "ARC",
    );
    await user.keyboard("{Enter}");
    const choice = await screen.findByRole("button", {
      name: /Alternate Reliability Charge/,
    });
    choice.focus();
    await user.keyboard("{Enter}");

    expect(lookupFixture.state.mutateAsync).toHaveBeenNthCalledWith(2, {
      mention: "test.arc-beta",
    });
    expect(
      await screen.findByRole("heading", {
        name: "Alternate Reliability Charge",
      }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?entity=test.arc-beta");
  });

  it("restores canonical entity route state on direct load", async () => {
    window.history.replaceState({}, "", "/ask?entity=in.central.dsm");
    lookupFixture.state.mutateAsync.mockResolvedValue(resolvedDsm);

    render(<ResearchWorkspace />);

    await waitFor(() =>
      expect(lookupFixture.state.mutateAsync).toHaveBeenCalledWith({
        mention: "in.central.dsm",
      }),
    );
    expect(
      await screen.findByRole("heading", {
        name: "Deviation Settlement Mechanism",
      }),
    ).toBeInTheDocument();
  });

  it("restores an owned previous-research route without entity lookup", async () => {
    window.history.replaceState(
      {},
      "",
      "/ask?session=22222222-2222-4222-8222-222222222222",
    );

    render(<ResearchWorkspace />);

    expect(
      await screen.findByText(
        "Session rail: 22222222-2222-4222-8222-222222222222",
      ),
    ).toBeInTheDocument();
    expect(lookupFixture.state.mutateAsync).not.toHaveBeenCalled();
  });

  it("shows no-match and safe failure states without inventing an entity", async () => {
    const user = userEvent.setup();
    lookupFixture.state.mutateAsync.mockResolvedValueOnce({
      ...resolvedDsm,
      status: "no_match",
      mention: "unknown",
      match_rule: "clarification",
      selected: null,
      candidates: [],
      clarification_question:
        "Which regulatory entity or jurisdiction do you mean?",
      surface: null,
    });
    render(<ResearchWorkspace />);

    await user.type(
      screen.getByLabelText("Ask a regulatory research question"),
      "unknown",
    );
    await user.keyboard("{Enter}");
    expect(
      await screen.findByRole("heading", {
        name: "No canonical entity matched",
      }),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Entity Intelligence Page"),
    ).not.toBeInTheDocument();

    lookupFixture.state.mutateAsync.mockRejectedValueOnce(
      new Error("raw provider failure"),
    );
    await user.type(
      screen.getByLabelText("Ask a regulatory research question"),
      "DSM",
    );
    await user.keyboard("{Enter}");
    expect(
      await screen.findByRole("alert"),
    ).toHaveTextContent("No database, provider, or diagnostic details");
    expect(screen.queryByText("raw provider failure")).not.toBeInTheDocument();
  });

  it("continues a healthy no-match with General AI knowledge", async () => {
    const user = userEvent.setup();
    lookupFixture.state.generalAvailable = true;
    lookupFixture.state.mutateAsync.mockResolvedValueOnce({
      ...resolvedDsm,
      status: "no_match",
      mention: "DSM",
      match_rule: "clarification",
      selected: null,
      candidates: [],
      clarification_question:
        "Which regulatory entity or jurisdiction do you mean?",
      surface: null,
    });
    lookupFixture.state.generalAsync.mockResolvedValueOnce({
      question: "DSM",
      reply:
        "DSM may refer to Demand-Side Management.\n\nThis explanation is generated from general AI knowledge because no sufficiently relevant official corpus evidence was selected for this question.",
      citations: 0,
    });
    render(<ResearchWorkspace />);

    await user.type(
      screen.getByLabelText("Ask a regulatory research question"),
      "DSM",
    );
    await user.keyboard("{Enter}");

    expect(
      await screen.findByText("General AI Knowledge"),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "This explanation is generated from general AI knowledge because no sufficiently relevant official corpus evidence was selected for this question.",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText("DSM may refer to Demand-Side Management."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", {
        name: "Search official documents manually",
      }),
    ).toHaveAttribute("href", "/browse");
    expect(
      screen.queryByRole("heading", { name: "No canonical entity matched" }),
    ).not.toBeInTheDocument();
    expect(lookupFixture.state.generalAsync).toHaveBeenCalledWith("DSM");
  });

  it("keeps a safe state when General AI cannot answer a no-match", async () => {
    const user = userEvent.setup();
    lookupFixture.state.generalAvailable = true;
    lookupFixture.state.mutateAsync.mockResolvedValueOnce({
      ...resolvedDsm,
      status: "no_match",
      mention: "DSM",
      match_rule: "clarification",
      selected: null,
      candidates: [],
      clarification_question:
        "Which regulatory entity or jurisdiction do you mean?",
      surface: null,
    });
    lookupFixture.state.generalAsync.mockRejectedValueOnce(
      new Error("raw provider failure"),
    );
    render(<ResearchWorkspace />);

    await user.type(
      screen.getByLabelText("Ask a regulatory research question"),
      "DSM",
    );
    await user.keyboard("{Enter}");

    expect(
      await screen.findByText("General explanation unavailable"),
    ).toBeInTheDocument();
    expect(screen.queryByText("raw provider failure")).not.toBeInTheDocument();
  });

  it("keeps submission honestly disabled when lookup capability is absent", () => {
    lookupFixture.state.available = false;
    render(<ResearchWorkspace />);

    expect(
      screen.getByRole("button", { name: "Start research" }),
    ).toBeDisabled();
    expect(
      screen.getByText(
        "Research submission is not enabled in this rollout.",
      ),
    ).toBeInTheDocument();
    expect(lookupFixture.state.mutateAsync).not.toHaveBeenCalled();
  });

  it("searches while typing and keyboard-selects an entity through canonical resolution", async () => {
    const user = userEvent.setup();
    lookupFixture.state.searchAvailable = true;
    lookupFixture.state.searchAsync.mockResolvedValue(
      federatedSearchFixture(),
    );
    lookupFixture.state.mutateAsync.mockResolvedValue(resolvedDsm);
    render(<ResearchWorkspace />);

    const composer = screen.getByLabelText(
      "Ask a regulatory research question",
    );
    await user.type(composer, "DSM");
    await waitFor(() =>
      expect(lookupFixture.state.searchAsync).toHaveBeenCalledWith({
        schema_version: "1",
        query: "DSM",
        correction_mode: "auto",
        filters: {},
        limit: 5,
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "Best Match" }),
    ).toBeInTheDocument();
    await user.click(
      screen.getByRole("button", { name: "Search original" }),
    );
    await waitFor(() =>
      expect(lookupFixture.state.searchAsync).toHaveBeenLastCalledWith({
        schema_version: "1",
        query: "DSM",
        correction_mode: "original",
        filters: {},
        limit: 5,
      }),
    );

    composer.focus();
    await user.keyboard("{ArrowDown}");
    expect(
      document.querySelector("[data-search-option]"),
    ).toHaveFocus();
    await user.keyboard("{Enter}");
    await waitFor(() =>
      expect(lookupFixture.state.mutateAsync).toHaveBeenCalledWith({
        mention: "in.central.dsm",
      }),
    );
    expect(window.location.search).toBe("?entity=in.central.dsm");
  });

  it("keeps the newest federated search result when an older request finishes later", async () => {
    const user = userEvent.setup();
    lookupFixture.state.searchAvailable = true;
    let resolveFirst:
      | ((value: ReturnType<typeof federatedSearchFixture>) => void)
      | undefined;
    let resolveSecond:
      | ((value: ReturnType<typeof federatedSearchFixture>) => void)
      | undefined;
    const first = new Promise<ReturnType<typeof federatedSearchFixture>>(
      (resolve) => {
        resolveFirst = resolve;
      },
    );
    const second = new Promise<ReturnType<typeof federatedSearchFixture>>(
      (resolve) => {
        resolveSecond = resolve;
      },
    );
    lookupFixture.state.searchAsync
      .mockReturnValueOnce(first)
      .mockReturnValueOnce(second);
    render(<ResearchWorkspace />);

    const composer = screen.getByLabelText(
      "Ask a regulatory research question",
    );
    await user.type(composer, "DS");
    await waitFor(() =>
      expect(lookupFixture.state.searchAsync).toHaveBeenCalledTimes(1),
    );
    await user.type(composer, "M");
    await waitFor(() =>
      expect(lookupFixture.state.searchAsync).toHaveBeenCalledTimes(2),
    );

    await act(async () => {
      resolveSecond?.(federatedSearchFixture());
      await second;
    });
    expect(
      await screen.findByText("Results for “DSM”"),
    ).toBeInTheDocument();

    const stale = federatedSearchFixture();
    stale.original_query = "DS";
    stale.applied_query = "DS";
    stale.correction = null;
    await act(async () => {
      resolveFirst?.(stale);
      await first;
    });
    expect(screen.getByText("Results for “DSM”")).toBeInTheDocument();
    expect(screen.queryByText("Results for “DS”")).not.toBeInTheDocument();
  });
});
