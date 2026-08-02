import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import responseContract from "../../../../api/backend/tests/fixtures/ask_response_contract.json";
import { ChangeResponseCard } from "./ChangeCards";

afterEach(() => cleanup());

function card(cardType: string): Record<string, unknown> {
  for (const section of responseContract.sections) {
    const found = section.cards.find((item) => item.card_type === cardType);
    if (found) return structuredClone(found) as Record<string, unknown>;
  }
  throw new Error(`Fixture card not found: ${cardType}`);
}

describe("Ask AI E8.4 change and intelligence cards", () => {
  it("renders a cited official timeline event and relationships", async () => {
    const user = userEvent.setup();
    const inspect = vi.fn();
    render(<ChangeResponseCard card={card("timeline_event")} actionHandlers={{ inspect_evidence: inspect }} />);
    const article = screen.getByRole("article", { name: "Timeline event" });
    expect(within(article).getByText("Revised filing rule became effective")).toBeInTheDocument();
    expect(within(article).getByText("Prior event: event-issued")).toBeInTheDocument();
    await user.click(within(article).getByRole("button", { name: "Inspect citation [2]" }));
    expect(inspect).toHaveBeenCalledWith("citation-2", expect.any(Object));
  });

  it("renders a live timeline event in the live lane with legal-status disclosure", () => {
    const timeline = card("timeline_event");
    const live = card("live_news");
    timeline.knowledge_mode = "live_intelligence";
    timeline.provenance_class = "live_web_sources";
    timeline.claim_ids = ["claim-live"];
    timeline.source_ids = ["source-live"];
    timeline.actions = [
      {
        action: "open_source",
        state: "available",
        target: "https://regulator.example/consultation",
        disabled_reason_code: null,
      },
    ];
    const payload = timeline.payload as Record<string, unknown>;
    payload.origin = "live";
    payload.source_label = { state: "established", value: "Regulator Newsroom" };
    payload.official_evidence_references = [];
    payload.live_source = structuredClone(
      (live.payload as Record<string, unknown>).live_source,
    );

    render(<ChangeResponseCard card={timeline} />);

    const article = screen.getByRole("article", { name: "Timeline event" });
    expect(within(article).getAllByText("Live Web Sources")).toHaveLength(2);
    expect(
      within(article).getByText(
        "Live reporting does not establish official legal status.",
      ),
    ).toBeInTheDocument();
  });

  it("renders amendment gaps and executes the exact compare target", async () => {
    const user = userEvent.setup();
    const compare = vi.fn();
    render(<ChangeResponseCard card={card("amendment")} actionHandlers={{ compare }} />);
    const article = screen.getByRole("article", { name: "Amendment" });
    expect(within(article).getByText("Not established")).toBeInTheDocument();
    await user.click(within(article).getByRole("button", { name: "Compare instruments" }));
    expect(compare).toHaveBeenCalledWith("source-1:source-2", expect.any(Object));
  });

  it("renders independently cited comparison sides and missing evidence", () => {
    render(<ChangeResponseCard card={card("comparison")} />);
    const table = screen.getByRole("table", { name: "Current instrument and Prior instrument comparison" });
    expect(within(table).getByRole("columnheader", { name: "Current instrument" })).toBeInTheDocument();
    expect(within(table).getByText("Monthly regulated-market participants")).toBeInTheDocument();
    expect(within(table).getAllByText("Not established")).toHaveLength(2);
    expect(within(table).getByText("[1] paragraph 4")).toBeInTheDocument();
  });

  it("renders live source identity, timestamps, disclosure, and official-basis action", async () => {
    const user = userEvent.setup();
    const findBasis = vi.fn();
    render(<ChangeResponseCard card={card("live_news")} actionHandlers={{ find_official_basis: findBasis }} />);
    const article = screen.getByRole("article", { name: "Live news" });
    expect(within(article).getByText("Regulator Newsroom")).toBeInTheDocument();
    expect(within(article).getByText("Live reporting does not establish official legal status.")).toBeInTheDocument();
    expect(within(article).getByRole("link", { name: "Open live source" })).toHaveAttribute("href", "https://regulator.example/consultation");
    await user.click(within(article).getByRole("button", { name: "Find official basis" }));
    expect(findBasis).toHaveBeenCalledWith("claim-live", expect.any(Object));
  });

  it("renders related regulation and opens its canonical intelligence page", async () => {
    const user = userEvent.setup();
    const openEntity = vi.fn();
    render(<ChangeResponseCard card={card("related_regulation")} actionHandlers={{ open_entity: openEntity }} />);
    expect(screen.getByText("This instrument revises paragraph 4 of the filing instrument.")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Open intelligence page" }));
    expect(openEntity).toHaveBeenCalledWith("entity-2", expect.any(Object));
  });

  it("never renders semantic actions without real handlers", () => {
    render(<ChangeResponseCard card={card("amendment")} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.getByText("[2a] amending clause")).toBeInTheDocument();
  });

  it("fails closed on unsafe live links and crossed comparison evidence", () => {
    const live = card("live_news");
    (live.payload as { live_source: { url: string } }).live_source.url = "http://unsafe.example/item";
    expect(() => render(<ChangeResponseCard card={live} />)).toThrow(/live_news payload/i);

    const comparison = card("comparison");
    comparison.source_ids = ["crossed-source"];
    expect(() => render(<ChangeResponseCard card={comparison} />)).toThrow(/envelope references/i);
  });

  it("refuses reuse of one citation identity across comparison sides", () => {
    const comparison = card("comparison");
    const dimension = (comparison.payload as {
      dimensions: Array<Record<string, unknown>>;
    }).dimensions[0];
    dimension.side_b = { state: "established", value: "Annual" };
    dimension.side_b_evidence_references = structuredClone(
      dimension.side_a_evidence_references,
    );

    expect(() => render(<ChangeResponseCard card={comparison} />)).toThrow(
      /comparison payload/i,
    );
  });
});
