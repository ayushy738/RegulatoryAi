import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FilterSelect } from "./Toolbar";

afterEach(() => {
  cleanup();
});

describe("FilterSelect", () => {
  it("keeps a stable labelled control when a long value is selected", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const options = [
      { value: "all", label: "Any stakeholder" },
      {
        value: "Transmission Licensees",
        label: "Transmission Licensees",
      },
    ];

    const { rerender, container } = render(
      <FilterSelect
        label="Stakeholder"
        value="all"
        options={options}
        onChange={onChange}
      />,
    );

    const idle = container.querySelector(".rv-select");
    expect(idle).not.toBeNull();
    expect(idle).not.toHaveClass("rv-select--active");
    expect(container.querySelector(".rv-select span:not(.rv-visually-hidden)")).toBeNull();

    await user.selectOptions(screen.getByLabelText("Stakeholder"), "Transmission Licensees");
    expect(onChange).toHaveBeenCalledWith("Transmission Licensees");

    rerender(
      <FilterSelect
        label="Stakeholder"
        value="Transmission Licensees"
        options={options}
        onChange={onChange}
      />,
    );

    const active = container.querySelector(".rv-select");
    expect(active).toHaveClass("rv-select--active");
    expect(active).toHaveAttribute("title", "Stakeholder: Transmission Licensees");
    expect(container.textContent).not.toMatch(/Stakeholder:/);
  });
});
