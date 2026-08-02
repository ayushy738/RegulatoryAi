import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import degradationContract from "../../../../api/backend/tests/fixtures/ask_degradation_contract.json";
import {
  askCapabilityDegradationSchema,
  type AskCapabilityDegradation,
} from "@/lib/ask-ai-degradation";

import { CapabilityDegradation } from "./CapabilityDegradation";

const contract = askCapabilityDegradationSchema.parse(degradationContract);

describe("CapabilityDegradation", () => {
  it("renders exact safe copy and executes only the named scoped action", async () => {
    const user = userEvent.setup();
    const onAction = vi.fn();
    render(<CapabilityDegradation value={contract} onAction={onAction} />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("data-capability", "regulatory_retriever");
    expect(status).toHaveAttribute("data-terminal-state", "unavailable");
    expect(status).toHaveAttribute("data-confidence-effect", "unknown");
    expect(status).toHaveTextContent("Official search temporarily unavailable");
    expect(status).not.toHaveTextContent("ASK_AI_OFFICIAL_COVERAGE_UNKNOWN");
    expect(status).not.toHaveTextContent("HTTP");

    const retry = screen.getByRole("button", { name: "Retry official search" });
    await user.tab();
    expect(retry).toHaveFocus();
    await user.keyboard("{Enter}");
    expect(onAction).toHaveBeenCalledWith(contract.actions[0]);

    expect(
      screen.getByRole("link", { name: "Search official documents manually" }),
    ).toHaveAttribute("href", "/browse");
  });

  it("renders no chrome for a deliberately hidden optional degradation", () => {
    const hidden = askCapabilityDegradationSchema.parse({
      ...degradationContract,
      capability: "follow_up_generator",
      terminal_state: "unavailable",
      signal: "unavailable",
      visible: false,
      severity: null,
      title: null,
      body: null,
      confidence_effect: "unchanged",
      safe_notice_code: "ASK_AI_FOLLOW_UPS_OMITTED",
      actions: [],
    });

    const { container } = render(<CapabilityDegradation value={hidden} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("requires a real handler before presenting command actions", () => {
    expect(() => render(<CapabilityDegradation value={contract} />)).toThrow(
      "require a handler",
    );
  });

  it("rejects crossed retries, unsafe links, and raw server detail", () => {
    const crossed = structuredClone(degradationContract);
    crossed.actions[0]!.capability = "news_retriever";
    expect(() => askCapabilityDegradationSchema.parse(crossed)).toThrow("crossed");

    const unsafe = structuredClone(degradationContract);
    unsafe.actions = [
      {
        action: "search_official_documents_manually",
        kind: "navigate",
        label: "Search official documents manually",
        target: "https://attacker.example",
        capability: null,
      },
    ];
    expect(() => askCapabilityDegradationSchema.parse(unsafe)).toThrow(
      "safe local path",
    );

    expect(() =>
      askCapabilityDegradationSchema.parse({
        ...degradationContract,
        raw_error: "provider secret",
      }),
    ).toThrow();
  });
});
