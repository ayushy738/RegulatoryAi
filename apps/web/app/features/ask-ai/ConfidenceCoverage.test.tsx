import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import {
  ConfidenceCoverage,
  type ConfidenceCoverageView,
} from "./ConfidenceCoverage";

afterEach(() => {
  cleanup();
});

function view(
  overrides: Partial<ConfidenceCoverageView> = {},
): ConfidenceCoverageView {
  return {
    score: 68,
    label: "medium",
    coveragePercent: 72,
    reasons: [
      {
        kind: "evidence",
        text: "Current official evidence supports the primary section.",
      },
      {
        kind: "coverage",
        text: "One requested background area has partial coverage.",
      },
    ],
    gaps: ["No verified official evidence covers the background estimate."],
    officialDocumentCount: 3,
    liveSourceCount: 1,
    corpusFreshness: "Official corpus updated 18 Jul 2026",
    improvements: ["Index the missing official filing."],
    sections: [
      {
        sectionId: "official",
        title: "Current official position",
        mode: "grounded_regulatory",
        score: 88,
        label: "high",
        coveragePercent: 94,
        critical: true,
        reasons: [
          {
            kind: "evidence",
            text: "Three current official instruments support the section.",
          },
        ],
        gaps: [],
      },
      {
        sectionId: "general",
        title: "Background explanation",
        mode: "general_ai",
        score: 75,
        label: "medium",
        coveragePercent: 61,
        critical: true,
        reasons: [
          {
            kind: "scope",
            text: "The explanation is bounded to general orientation.",
          },
        ],
        gaps: ["No official citation is available for this section."],
      },
      {
        sectionId: "live",
        title: "Latest reporting",
        mode: "live_intelligence",
        score: 58,
        label: "low",
        coveragePercent: 45,
        critical: false,
        reasons: [
          {
            kind: "freshness",
            text: "One attributed live source was retrieved today.",
          },
        ],
        gaps: ["Independent live confirmation is not available."],
      },
    ],
    ...overrides,
  };
}

describe("Ask AI confidence and coverage", () => {
  it("renders an accessible collapsed indicator with exact score and coverage", () => {
    render(<ConfidenceCoverage view={view()} />);

    const card = screen.getByRole("region", {
      name: "Confidence and coverage",
    });
    expect(
      within(card).getAllByText("Medium confidence")[0],
    ).toBeInTheDocument();
    expect(
      within(card).getByText("Useful evidence with stated limits."),
    ).toBeInTheDocument();
    expect(
      within(card).getByText(
        "This evidence confidence score is not a probability of legal correctness.",
      ),
    ).toBeInTheDocument();
    expect(
      within(card).getByText("Mixed — Multiple provenance modes"),
    ).toBeInTheDocument();
    expect(
      within(card).getByRole("meter", { name: "Overall confidence score" }),
    ).toHaveAttribute("aria-valuenow", "68");
    expect(
      within(card).getByRole("meter", { name: "Overall evidence coverage" }),
    ).toHaveAttribute("aria-valuenow", "72");

    const button = within(card).getByRole("button", {
      name: "Why this confidence?",
    });
    const panel = document.getElementById(
      button.getAttribute("aria-controls") ?? "",
    );
    expect(button).toHaveAttribute("aria-expanded", "false");
    expect(panel).toHaveAttribute("hidden");
  });

  it("opens evidence reasons, gaps, improvements, and source coverage", async () => {
    const user = userEvent.setup();
    render(<ConfidenceCoverage view={view()} />);

    await user.click(
      screen.getByRole("button", { name: "Why this confidence?" }),
    );

    expect(
      screen.getByRole("button", { name: "Hide explanation" }),
    ).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("Official documents found")).toBeInTheDocument();
    expect(screen.getByText("Live sources found")).toBeInTheDocument();
    expect(
      screen.getByText("Official corpus updated 18 Jul 2026"),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "What evidence is missing" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "What would improve confidence" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Index the missing official filing.")).toBeInTheDocument();
  });

  it("keeps mixed-mode section confidence and gaps independently visible", async () => {
    const user = userEvent.setup();
    render(<ConfidenceCoverage view={view()} />);
    await user.click(
      screen.getByRole("button", { name: "Why this confidence?" }),
    );

    const sections = screen.getAllByRole("article");
    expect(sections).toHaveLength(3);
    expect(sections[0]).toHaveAttribute("data-mode", "grounded_regulatory");
    expect(sections[1]).toHaveAttribute("data-mode", "general_ai");
    expect(sections[2]).toHaveAttribute("data-mode", "live_intelligence");
    expect(
      within(sections[0]).getByText("Official Regulatory Corpus"),
    ).toBeInTheDocument();
    expect(
      within(sections[1]).getByText("General AI Knowledge"),
    ).toBeInTheDocument();
    expect(
      within(sections[2]).getByText("Live Web Sources"),
    ).toBeInTheDocument();
    expect(
      within(sections[1]).getByText(
        "No official citation is available for this section.",
      ),
    ).toBeInTheDocument();
  });

  it("shows critical status and confidence without relying on color", async () => {
    const user = userEvent.setup();
    render(<ConfidenceCoverage view={view()} />);
    await user.click(
      screen.getByRole("button", { name: "Why this confidence?" }),
    );

    const official = screen.getByRole("article", {
      name: "Current official position",
    });
    expect(official).toHaveAttribute("data-critical", "true");
    expect(within(official).getByText("Critical section")).toBeInTheDocument();
    expect(within(official).getByText("High confidence")).toBeInTheDocument();
    expect(
      within(official).getByRole("meter", {
        name: "Current official position confidence score",
      }),
    ).toHaveAttribute("aria-valuetext", "88.0 out of 100");
  });

  it("allows a lower policy ceiling than the numeric band", () => {
    const capped = view({
      score: 90,
      label: "medium",
      sections: view().sections.map((section) =>
        section.sectionId === "general"
          ? { ...section, score: 90, label: "medium" }
          : section,
      ),
    });

    expect(() => render(<ConfidenceCoverage view={capped} />)).not.toThrow();
    expect(screen.getAllByText("Medium confidence")[0]).toBeInTheDocument();
  });

  it("renders hard Unknown explicitly even when the numeric score is high", () => {
    const unknownSections = view().sections.map((section) =>
      section.sectionId === "general"
        ? { ...section, score: 90, label: "unknown" as const }
        : section,
    );
    render(
      <ConfidenceCoverage
        view={view({
          score: 90,
          label: "unknown",
          sections: unknownSections,
        })}
      />,
    );

    expect(screen.getAllByText("Unknown confidence")[0]).toBeInTheDocument();
    expect(
      screen.getByText(
        "Confidence cannot be established from available evidence.",
      ),
    ).toBeInTheDocument();
  });

  it("refuses a label above its numeric band or General AI ceiling", () => {
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ score: 79, label: "high" })} />,
      ),
    ).toThrow("cannot exceed its numeric confidence band");

    const sections = view().sections.map((section) =>
      section.sectionId === "general"
        ? { ...section, score: 90, label: "high" as const }
        : section,
    );
    expect(() =>
      render(<ConfidenceCoverage view={view({ sections })} />),
    ).toThrow("General AI confidence cannot be High");
  });

  it("refuses overall confidence above the weakest critical section", () => {
    expect(() =>
      render(
        <ConfidenceCoverage
          view={view({
            score: 90,
            label: "high",
          })}
        />,
      ),
    ).toThrow("cannot exceed a critical section");
  });

  it("requires evidence-based reasons, unique identities, and a critical section", () => {
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ reasons: [] })} />,
      ),
    ).toThrow("requires evidence-based reasons");

    const duplicateSections = [
      ...view().sections,
      { ...view().sections[0] },
    ];
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ sections: duplicateSections })} />,
      ),
    ).toThrow("section IDs must be unique");

    expect(() =>
      render(
        <ConfidenceCoverage
          view={view({
            sections: view().sections.map((section) => ({
              ...section,
              critical: false,
            })),
          })}
        />,
      ),
    ).toThrow("requires a critical section");
  });

  it("refuses nonfinite scores, invalid coverage, and duplicate gaps", () => {
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ score: Number.NaN })} />,
      ),
    ).toThrow("must be finite");
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ coveragePercent: 101 })} />,
      ),
    ).toThrow("between 0 and 100");
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ gaps: ["Missing", "Missing"] })} />,
      ),
    ).toThrow("gaps must be unique");
  });

  it("requires source counts to match the displayed provenance modes", () => {
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ officialDocumentCount: 0 })} />,
      ),
    ).toThrow("Official document count must match");
    expect(() =>
      render(
        <ConfidenceCoverage view={view({ liveSourceCount: 0 })} />,
      ),
    ).toThrow("Live source count must match");
  });

  it("rejects introspection and uses generated accessible section identity", async () => {
    expect(() =>
      render(
        <ConfidenceCoverage
          view={view({
            reasons: [
              {
                kind: "evidence",
                text: "The model reasoning says this is probably correct.",
              },
            ],
          })}
        />,
      ),
    ).toThrow("cannot expose model introspection");

    const user = userEvent.setup();
    const sections = view().sections.map((section, index) =>
      index === 0 ? { ...section, sectionId: "unsafe id #1" } : section,
    );
    render(<ConfidenceCoverage view={view({ sections })} />);
    await user.click(
      screen.getByRole("button", { name: "Why this confidence?" }),
    );
    expect(
      screen.getByRole("article", { name: "Current official position" }),
    ).toBeInTheDocument();
  });

  it("supports keyboard disclosure and restores the collapsed state", async () => {
    const user = userEvent.setup();
    render(<ConfidenceCoverage view={view()} />);

    await user.tab();
    const button = screen.getByRole("button", {
      name: "Why this confidence?",
    });
    expect(button).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(button).toHaveAttribute("aria-expanded", "true");
    await user.keyboard("{Enter}");
    expect(
      screen.getByRole("button", { name: "Why this confidence?" }),
    ).toHaveAttribute("aria-expanded", "false");
  });
});
