import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntelligenceCard } from "./IntelligenceCard";
import type { DigestEvent } from "@/lib/api";

afterEach(() => {
  cleanup();
});

function event(overrides: Partial<DigestEvent> = {}): DigestEvent {
  return {
    id: 42,
    title: "Draft tariff amendment for renewable energy",
    issuing_body: "Central Electricity Regulatory Commission",
    jurisdiction: "central",
    issue_date: "2026-08-11",
    event_type: "NEW",
    topic_tags: ["Tariff"],
    raw_summary: "A draft amendment was published.",
    summary: {
      plain_english_summary: "CERC published a draft tariff amendment.",
      why_it_matters: "It changes how renewable generators recover costs.",
      affected_segments: ["Solar Developers"],
      important_dates: ["2026-08-11"],
      action_required: "monitor",
      confidence: "high",
      evidence_quotes: [],
    },
    source_url: "https://cerc.gov.in/draft",
    detected_at: "2026-08-11T10:00:00Z",
    is_read: false,
    is_bookmarked: false,
    ...overrides,
  };
}

describe("IntelligenceCard", () => {
  it("keeps the same structural regions when metadata is sparse", () => {
    const sparse = event({
      topic_tags: [],
      summary: {
        plain_english_summary: "Short.",
        why_it_matters: "",
        affected_segments: [],
        important_dates: [],
        action_required: "none",
        confidence: "low",
        evidence_quotes: [],
      },
    });

    const { container: dense } = render(
      <IntelligenceCard event={event()} onBookmark={() => undefined} />,
    );
    const { container: empty } = render(
      <IntelligenceCard event={sparse} onBookmark={() => undefined} />,
    );

    for (const root of [dense, empty]) {
      const card = root.querySelector(".rv-intel-card");
      expect(card).not.toBeNull();
      expect(card?.querySelector(".rv-intel-card__head")).not.toBeNull();
      expect(card?.querySelector(".rv-intel-card__title")).not.toBeNull();
      expect(card?.querySelector(".rv-intel-card__summary")).not.toBeNull();
      expect(card?.querySelector(".rv-intel-card__tags")).not.toBeNull();
      expect(card?.querySelector(".rv-intel-card__footer")).not.toBeNull();
      expect(card?.querySelector(".rv-intel-card__open")).not.toBeNull();
    }
  });

  it("opens the canonical event detail route", () => {
    render(<IntelligenceCard event={event()} onBookmark={() => undefined} />);
    expect(screen.getByRole("link", { name: /Open/ })).toHaveAttribute(
      "href",
      "/events/42",
    );
  });

  it("shows a pending Save action until the backend confirms Saved", async () => {
    const onBookmark = vi.fn();
    const user = userEvent.setup();
    const { rerender } = render(
      <IntelligenceCard event={event()} onBookmark={onBookmark} />,
    );

    expect(screen.getByRole("button", { name: "Save" })).toHaveAttribute(
      "aria-pressed",
      "false",
    );
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(onBookmark).toHaveBeenCalledTimes(1);

    rerender(
      <IntelligenceCard
        event={event({ is_bookmarked: true })}
        onBookmark={onBookmark}
        busy
      />,
    );
    expect(screen.getByRole("button", { name: "Saved" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Saved" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});
