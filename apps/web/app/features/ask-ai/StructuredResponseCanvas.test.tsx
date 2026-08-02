import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import responseContract from "../../../../api/backend/tests/fixtures/ask_response_contract.json";

import { StructuredResponseCanvas } from "./StructuredResponseCanvas";

afterEach(cleanup);

describe("StructuredResponseCanvas", () => {
  it("renders ordered provenance-pure sections and every known card family", () => {
    render(<StructuredResponseCanvas response={responseContract} />);

    expect(
      screen.getByRole("heading", {
        level: 2,
        name: /The filing obligation is in force/,
      }),
    ).toBeInTheDocument();
    const sections = screen.getAllByRole("article").filter((item) =>
      item.classList.contains("ask-structured-section"),
    );
    expect(sections).toHaveLength(3);
    expect(sections.map((item) => item.getAttribute("data-mode"))).toEqual([
      "grounded_regulatory",
      "live_intelligence",
      "general_ai",
    ]);
    expect(screen.getAllByText("Official Regulatory Corpus").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Live Web Sources").length).toBeGreaterThan(0);
    expect(screen.getAllByText("General AI Knowledge").length).toBeGreaterThan(0);
    for (const name of [
      "Obligation",
      "Deadline",
      "Stakeholder",
      "Timeline event",
      "Amendment",
      "Comparison",
      "Live news",
      "Related regulation",
      "Unsupported card",
    ]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
    expect(screen.queryByText("north")).not.toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Overall response confidence" })).toHaveAttribute(
      "aria-valuenow",
      "84",
    );
    expect(screen.getByRole("meter", { name: "Live updates confidence" })).toHaveAttribute(
      "aria-valuenow",
      "68",
    );
    expect(screen.getByText("Official confirmation is pending.")).toBeInTheDocument();
    expect(screen.getByText("Degraded")).toBeInTheDocument();
  });

  it("executes only injected real actions and leaves unhandled actions hidden", async () => {
    const user = userEvent.setup();
    const openSource = vi.fn();
    const inspectEvidence = vi.fn();
    render(
      <StructuredResponseCanvas
        response={responseContract}
        actionHandlers={{
          open_source: openSource,
          inspect_evidence: inspectEvidence,
        }}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Open" }));
    await user.click(
      screen.getAllByRole("button", { name: "Inspect citation [1]" })[0],
    );

    expect(openSource).toHaveBeenCalledWith(
      "source-1",
      expect.objectContaining({ card_id: "card-source" }),
    );
    expect(inspectEvidence).toHaveBeenCalledWith(
      "citation-1",
      expect.objectContaining({ card_id: "card-obligation" }),
    );
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compare" })).toBeDisabled();
  });

  it("keeps non-content terminal sections visible without inventing cards", () => {
    const response = structuredClone(responseContract);
    response.sections[0].cards = [];
    response.sections[0].state = "empty_by_evidence";

    render(<StructuredResponseCanvas response={response} />);

    expect(screen.getByText("No evidence found")).toBeInTheDocument();
    expect(
      screen.getByText(/No structured cards are available for this section/),
    ).toBeInTheDocument();
    expect(screen.queryByText("Every regulated entity must submit"))
      .not.toBeInTheDocument();
  });

  it("does not render model-introspection confidence text", () => {
    const response = structuredClone(responseContract);
    response.overall_confidence.reasons = ["The system prompt contains hidden reasoning."];
    response.sections[0].confidence.reasons = ["I think this result is correct."];

    render(<StructuredResponseCanvas response={response} />);

    expect(screen.queryByText(/system prompt/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/I think this result/i)).not.toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Overall response confidence" }))
      .toBeInTheDocument();
  });
});
