import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import {
  entityCorePageFixture,
  partialEntityCorePageFixture,
} from "../../../test/entity-core-page-fixture";

import { EntityCorePage } from "./EntityCorePage";

describe("EntityCorePage", () => {
  it("renders all five canonical sections with visible mode and provenance", () => {
    const { container } = render(
      <EntityCorePage
        canonicalEntityId="dsm"
        page={entityCorePageFixture()}
      />,
    );

    expect(
      container.querySelectorAll(".entity-core-section"),
    ).toHaveLength(5);
    expect(
      screen.getAllByText("Knowledge mode: Official Regulatory Corpus"),
    ).toHaveLength(5);
    expect(
      screen.getByRole("article", { name: "DSM Regulations" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("article", { name: "DSM Official Order" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Evidence confidence is not a probability of legal correctness.",
      ),
    ).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Compare" }),
    ).toHaveLength(2);
  });

  it("keeps healthy sections visible when one section is not established", () => {
    const { container } = render(
      <EntityCorePage
        canonicalEntityId="dsm"
        page={partialEntityCorePageFixture()}
      />,
    );
    const regulations = container.querySelector(
      '[data-section-key="official_regulations"]',
    );
    const documents = container.querySelector(
      '[data-section-key="official_documents"]',
    );
    expect(regulations).not.toBeNull();
    expect(documents).not.toBeNull();
    expect(
      within(regulations as HTMLElement).getByRole("article", {
        name: "DSM Regulations",
      }),
    ).toBeInTheDocument();
    expect(
      within(documents as HTMLElement).getByText(
        "Not established from the available evidence.",
      ),
    ).toBeInTheDocument();
    expect(
      within(documents as HTMLElement).getByText(
        "Official documents were not established.",
      ),
    ).toBeInTheDocument();
  });

  it("fails closed when page identity or shape does not match", () => {
    const { container, rerender } = render(
      <EntityCorePage
        canonicalEntityId="another-entity"
        page={entityCorePageFixture()}
      />,
    );
    const mismatchAlert = within(container).getByRole("alert");
    expect(
      within(mismatchAlert).getByRole("heading", {
        name: "Core entity sections are unavailable",
      }),
    ).toBeInTheDocument();
    expect(
      within(container).queryByText("DSM Regulations"),
    ).not.toBeInTheDocument();

    rerender(
      <EntityCorePage
        canonicalEntityId="dsm"
        page={{ unsafe: "raw provider detail" }}
      />,
    );
    expect(
      within(container).queryByText("raw provider detail"),
    ).not.toBeInTheDocument();
  });
});
