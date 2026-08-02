import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import responseContract from "../../../../api/backend/tests/fixtures/ask_response_contract.json";
import { ComplianceResponseCard } from "./ComplianceCards";

afterEach(() => cleanup());

function card(cardType: string): Record<string, unknown> {
  for (const section of responseContract.sections) {
    const found = section.cards.find((item) => item.card_type === cardType);
    if (found) return structuredClone(found) as Record<string, unknown>;
  }
  throw new Error(`Fixture card not found: ${cardType}`);
}

describe("Ask AI E8.3 compliance cards", () => {
  it("renders a complete cited obligation with real actions", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    const applicability = vi.fn();
    render(
      <ComplianceResponseCard
        card={card("obligation")}
        actionHandlers={{ inspect_evidence: inspect, check_applicability: applicability }}
      />,
    );
    const article = screen.getByRole("article", { name: "Obligation" });
    expect(within(article).getByText("Regulated entity")).toBeInTheDocument();
    expect(within(article).getByText("Submit the prescribed filing")).toBeInTheDocument();
    await user.click(within(article).getByRole("button", { name: "Inspect citation [1]" }));
    expect(inspect).toHaveBeenCalledWith("citation-1", expect.any(Object));
    await user.click(within(article).getByRole("button", { name: "Check applicability" }));
    expect(applicability).toHaveBeenCalledWith("claim-1", expect.any(Object));
  });

  it("renders an unverified deadline as Not established with disabled tracking", () => {
    render(<ComplianceResponseCard card={card("deadline")} />);
    const article = screen.getByRole("article", { name: "Deadline" });
    expect(within(article).getAllByText("Not established").length).toBeGreaterThan(2);
    expect(within(article).getByText("Unverified")).toBeInTheDocument();
    expect(within(article).getByText("Official basis not established.")).toBeInTheDocument();
    expect(within(article).getByRole("button", { name: "Add to tracker — unavailable" })).toBeDisabled();
  });

  it("renders stakeholder impact, obligations, regulations, coverage, and entity action", async () => {
    const user = userEvent.setup();
    const openEntity = vi.fn();
    render(
      <ComplianceResponseCard
        card={card("stakeholder")}
        actionHandlers={{ open_entity: openEntity }}
      />,
    );
    const article = screen.getByRole("article", { name: "Stakeholder" });
    expect(within(article).getByText("Filing party")).toBeInTheDocument();
    expect(within(article).getByText("Submit the prescribed filing")).toBeInTheDocument();
    expect(within(article).getByRole("meter", { name: "Stakeholder evidence coverage" })).toHaveAttribute("aria-valuenow", "75");
    await user.click(within(article).getByRole("button", { name: "Open stakeholder" }));
    expect(openEntity).toHaveBeenCalledWith("entity-1", expect.any(Object));
  });

  it("never renders available actions without real handlers", () => {
    render(<ComplianceResponseCard card={card("obligation")} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("[1] paragraph 4")).toBeInTheDocument();
  });

  it("fails closed on crossed evidence and provenance", () => {
    const crossed = card("obligation");
    crossed.source_ids = ["crossed-source"];
    expect(() => render(<ComplianceResponseCard card={crossed} />)).toThrow(/envelope references/i);

    const general = card("stakeholder");
    general.knowledge_mode = "general_ai";
    general.provenance_class = "general_ai_knowledge";
    expect(() => render(<ComplianceResponseCard card={general} />)).toThrow(/grounded/i);
  });

  it("accepts one claim supported by multiple distinct official sources", () => {
    const obligation = card("obligation");
    obligation.source_ids = ["source-1", "source-2"];
    const payload = obligation.payload as {
      evidence_references: Array<Record<string, unknown>>;
    };
    payload.evidence_references.push({
      citation_id: "citation-2",
      claim_id: "claim-1",
      source_id: "source-2",
      marker: "[2]",
      locator: { state: "established", value: "section 8" },
    });

    render(<ComplianceResponseCard card={obligation} />);

    expect(screen.getByText("[2] section 8")).toBeInTheDocument();
  });
});
