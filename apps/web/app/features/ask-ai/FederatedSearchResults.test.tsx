import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { federatedSearchFixture } from "../../../test/federated-search-fixture";

import { FederatedSearchResults } from "./FederatedSearchResults";

afterEach(cleanup);

describe("FederatedSearchResults", () => {
  it("renders canonical groups, provenance reasons, correction, and filters", async () => {
    const user = userEvent.setup();
    const onRestoreOriginal = vi.fn();
    const onFiltersChange = vi.fn();
    render(
      <FederatedSearchResults
        result={federatedSearchFixture()}
        pending={false}
        error={null}
        onSelect={vi.fn()}
        onRestoreOriginal={onRestoreOriginal}
        filters={{}}
        onFiltersChange={onFiltersChange}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Best Match" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("heading", { name: "Entities" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByText("Approved entity alias or acronym matched."),
    ).toHaveLength(2);
    expect(
      screen.getByText(/Interpreted as/),
    ).toHaveTextContent("Deviation Settlement Mechanism");
    expect(screen.getByLabelText("Provenance")).toBeInTheDocument();
    expect(screen.getByLabelText("Lifecycle")).toBeInTheDocument();
    expect(screen.getByLabelText("Stakeholder")).toBeInTheDocument();
    expect(screen.getByLabelText("Topic")).toBeInTheDocument();

    await user.click(
      screen.getByRole("button", { name: "Search original" }),
    );
    expect(onRestoreOriginal).toHaveBeenCalledWith("DSM");

    await user.type(screen.getByLabelText("Regulator"), "C");
    expect(onFiltersChange).toHaveBeenLastCalledWith({
      regulator: "C",
    });
  });

  it("supports option arrow navigation, escape, and selection", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(
      <>
        <div className="research-workspace-composer">
          <textarea aria-label="Composer" />
        </div>
        <FederatedSearchResults
          result={federatedSearchFixture()}
          pending={false}
          error={null}
          onSelect={onSelect}
          onRestoreOriginal={vi.fn()}
          filters={{}}
          onFiltersChange={vi.fn()}
        />
      </>,
    );
    const options = Array.from(
      document.querySelectorAll<HTMLButtonElement>(
        "[data-search-option]",
      ),
    );

    options[0]!.focus();
    await user.keyboard("{ArrowDown}");
    expect(options[1]).toHaveFocus();
    await user.keyboard("{ArrowUp}");
    expect(options[0]).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(screen.getByLabelText("Composer")).toHaveFocus();
    options[0]!.focus();
    await user.keyboard("{Enter}");
    expect(onSelect).toHaveBeenCalledWith(
      federatedSearchFixture().groups[0]!.items[0],
    );
  });

  it("keeps pending, no-match, and failure states explicit", () => {
    const props = {
      onSelect: vi.fn(),
      onRestoreOriginal: vi.fn(),
      filters: {},
      onFiltersChange: vi.fn(),
    };
    const { rerender } = render(
      <FederatedSearchResults
        {...props}
        result={null}
        pending
        error={null}
      />,
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "Searching canonical research sources",
    );

    const empty = federatedSearchFixture();
    empty.groups = empty.groups.map((group) => ({
      ...group,
      status: "no_match" as const,
      items: [],
      next_cursor: null,
    }));
    rerender(
      <FederatedSearchResults
        {...props}
        result={empty}
        pending={false}
        error={null}
      />,
    );
    expect(
      screen.getByText(/No matching canonical research result/),
    ).toBeInTheDocument();

    rerender(
      <FederatedSearchResults
        {...props}
        result={null}
        pending={false}
        error="Try again without exposing provider details."
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Research search is unavailable",
    );
  });
});
