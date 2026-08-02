import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import responseContract from "../../../../api/backend/tests/fixtures/ask_response_contract.json";
import { askResponseCardSchema } from "../../../lib/ask-ai-response";
import { CoreResponseCard } from "./CoreCards";

afterEach(() => {
  cleanup();
});

function card(
  cardType: string,
  sectionIndex = 0,
): Record<string, unknown> {
  const section = responseContract.sections[sectionIndex];
  const found = section.cards.find((item) => item.card_type === cardType);
  if (!found) throw new Error(`Fixture card not found: ${cardType}`);
  return structuredClone(found) as Record<string, unknown>;
}

describe("Ask AI E8.2 core cards", () => {
  it("renders a provenance-visible Answer Summary with its required fields", () => {
    render(<CoreResponseCard card={card("answer_summary")} />);

    const summary = screen.getByRole("article", { name: "Answer summary" });
    expect(
      within(summary).getByText("Official Regulatory Corpus"),
    ).toBeInTheDocument();
    expect(within(summary).getByText("Ready")).toBeInTheDocument();
    expect(
      within(summary).getByText("The filing obligation is in force."),
    ).toBeInTheDocument();
    expect(
      within(summary).getByRole("heading", { name: "Why it matters" }),
    ).toBeInTheDocument();
    expect(within(summary).getByText("1 source")).toBeInTheDocument();
  });

  it("renders every Definition field and names missing data explicitly", () => {
    render(<CoreResponseCard card={card("definition")} />);

    const definition = screen.getByRole("article", { name: "Definition" });
    expect(
      within(definition).getByText(
        "An entity subject to the instrument's filing requirement.",
      ),
    ).toBeInTheDocument();
    expect(
      within(definition).getByText(
        "An organization that must follow the filing rule.",
      ),
    ).toBeInTheDocument();
    expect(
      within(definition).getByText("Acronym expansion"),
    ).toBeInTheDocument();
    expect(within(definition).getByText("Not established")).toHaveAttribute(
      "data-field-state",
      "not_established",
    );
  });

  it("renders complete official metadata, evidence, and only honest actions", async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    const save = vi.fn();
    render(
      <CoreResponseCard
        card={card("official_source")}
        actionHandlers={{ open_source: open, save }}
      />,
    );

    const source = screen.getByRole("article", { name: "Official source" });
    expect(
      within(source).getByText("Regulatory Filing Instrument"),
    ).toBeInTheDocument();
    expect(
      within(source).getByText("Central Regulatory Commission"),
    ).toBeInTheDocument();
    expect(within(source).getByText("In force")).toBeInTheDocument();
    expect(
      within(source).getByText(
        "Every regulated entity must submit the prescribed filing.",
      ),
    ).toBeInTheDocument();

    await user.click(within(source).getByRole("button", { name: "Open" }));
    expect(open).toHaveBeenCalledWith("source-1", expect.any(Object));
    await user.click(within(source).getByRole("button", { name: "Save" }));
    expect(save).toHaveBeenCalledWith("source-1", expect.any(Object));
    expect(
      within(source).getByRole("button", { name: "Compare" }),
    ).toBeDisabled();
    expect(
      within(source).getByText(
        "Unavailable — this behavior is not enabled.",
      ),
    ).toBeInTheDocument();
  });

  it("hides available actions when no real handler is supplied", () => {
    render(<CoreResponseCard card={card("official_source")} />);

    const source = screen.getByRole("article", { name: "Official source" });
    expect(
      within(source).queryByRole("button", { name: "Open" }),
    ).not.toBeInTheDocument();
    expect(
      within(source).queryByRole("button", { name: "Save" }),
    ).not.toBeInTheDocument();
    expect(
      within(source).getByRole("button", { name: "Compare" }),
    ).toBeDisabled();
  });

  it("renders evidence confidence, coverage, reasons, gaps, and improvement", () => {
    render(<CoreResponseCard card={card("confidence_coverage")} />);

    const confidence = screen.getByRole("article", {
      name: "Confidence and coverage",
    });
    expect(
      within(confidence).getByText("high confidence · 92.5 out of 100"),
    ).toBeInTheDocument();
    expect(
      within(confidence).getByRole("meter", {
        name: "Confidence and coverage evidence coverage",
      }),
    ).toHaveAttribute("aria-valuenow", "92.5");
    expect(
      within(confidence).getByText(
        "Evidence confidence is not a probability of legal correctness.",
      ),
    ).toBeInTheDocument();
    expect(
      within(confidence).getByText(
        "Two current official sources support the material claims.",
      ),
    ).toBeInTheDocument();
    expect(
      within(confidence).getByRole("heading", {
        name: "Unsupported or inferred areas",
      }),
    ).toBeInTheDocument();
    expect(
      within(confidence).getByRole("heading", {
        name: "What would improve confidence",
      }),
    ).toBeInTheDocument();
  });

  it("keeps separate confidence cards for separate provenance modes", () => {
    const official = card("confidence_coverage");
    const general = card("confidence_coverage");
    general.card_id = "card-confidence-general";
    general.title = "General confidence";
    general.knowledge_mode = "general_ai";
    general.provenance_class = "general_ai_knowledge";
    general.source_ids = [];
    general.confidence = {
      score: 72,
      label: "medium",
      reasons: ["General AI has no official evidence."],
    };
    general.payload = {
      schema_version: "1",
      modes_used: ["general_ai"],
      coverage_percent: 0,
      official_documents_found: 0,
      live_sources_found: 0,
      reasons: [
        {
          kind: "evidence",
          text: "General AI has no official evidence.",
        },
      ],
      unsupported_or_inferred_areas: ["No official basis was established."],
      corpus_freshness: { state: "not_established", value: null },
      what_would_improve_confidence: ["Find an official source."],
    };

    render(
      <>
        <CoreResponseCard card={official} />
        <CoreResponseCard card={general} />
      </>,
    );

    const officialCard = screen.getByRole("article", {
      name: "Confidence and coverage",
    });
    const generalCard = screen.getByRole("article", {
      name: "General confidence",
    });
    expect(
      within(officialCard).getAllByText("Official Regulatory Corpus").length,
    ).toBeGreaterThan(0);
    expect(
      within(generalCard).getAllByText("General AI Knowledge").length,
    ).toBeGreaterThan(0);
    expect(
      within(generalCard).queryByText("Official Regulatory Corpus"),
    ).not.toBeInTheDocument();
  });

  it("renders partial official fields as Not established without guessing", () => {
    const source = card("official_source");
    source.state = "partial";
    source.payload = {
      ...(source.payload as Record<string, unknown>),
      effective_date: { state: "not_established", value: null },
    };
    render(<CoreResponseCard card={source} />);

    const rendered = screen.getByRole("article", { name: "Official source" });
    expect(
      within(rendered).getByText("Partial — some fields are not established"),
    ).toBeInTheDocument();
    expect(within(rendered).getByText("Not established")).toHaveAttribute(
      "data-field-state",
      "not_established",
    );
  });

  it("supports keyboard activation for a real card action", async () => {
    const user = userEvent.setup();
    const open = vi.fn();
    render(
      <CoreResponseCard
        card={card("official_source")}
        actionHandlers={{ open_source: open }}
      />,
    );

    await user.tab();
    expect(screen.getByRole("button", { name: "Open" })).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(open).toHaveBeenCalledWith("source-1", expect.any(Object));
  });

  it("rejects generic payloads, source crossing, and confidence introspection", () => {
    const generic = card("answer_summary");
    generic.payload = { content: "Old generic JSON" };

    const crossed = card("official_source");
    crossed.knowledge_mode = "general_ai";
    crossed.provenance_class = "general_ai_knowledge";

    const summaryCrossed = card("answer_summary");
    summaryCrossed.provenance_class = "general_ai_knowledge";

    const elevated = card("answer_summary");
    elevated.confidence = {
      score: 40,
      label: "high",
      reasons: [],
    };

    const introspection = card("confidence_coverage");
    introspection.confidence = {
      score: 92.5,
      label: "high",
      reasons: ["My hidden chain of thought establishes confidence."],
    };
    introspection.payload = {
      ...(introspection.payload as Record<string, unknown>),
      reasons: [
        {
          kind: "evidence",
          text: "My hidden chain of thought establishes confidence.",
        },
      ],
    };

    for (const invalid of [
      generic,
      crossed,
      summaryCrossed,
      elevated,
      introspection,
    ]) {
      expect(() => askResponseCardSchema.parse(invalid)).toThrow();
    }
  });

  it("rejects non-core cards at the isolated renderer boundary", () => {
    expect(() =>
      render(<CoreResponseCard card={card("obligation")} />),
    ).toThrow("CoreResponseCard supports only E8.2 card types");
  });
});
