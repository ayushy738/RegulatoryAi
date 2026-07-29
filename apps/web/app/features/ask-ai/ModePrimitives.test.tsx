import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import {
  GeneralAiDisclosure,
  KnowledgeModeBanner,
  KnowledgeModeSection,
  LIVE_REFRESH_UNAVAILABLE_NOTICE,
  LiveSourceCard,
  ModeStatePanel,
  NO_OFFICIAL_DOCUMENTS_DISCLOSURE,
  NO_VERIFIED_LIVE_UPDATES_NOTICE,
  OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE,
} from "./ModePrimitives";

afterEach(() => {
  cleanup();
});

describe("Ask AI knowledge-mode primitives", () => {
  it("freezes the E6.1 disclosure and live-state copy", () => {
    expect(NO_OFFICIAL_DOCUMENTS_DISCLOSURE).toBe(
      "This explanation is generated from general AI knowledge because no official regulatory documents were found.",
    );
    expect(OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE).toBe(
      "Official document search is temporarily unavailable. You can still view previously retrieved sources or search documents manually. Any explanation generated now will be labeled as general AI knowledge.",
    );
    expect(NO_VERIFIED_LIVE_UPDATES_NOTICE).toBe(
      "No verified live updates were found for this period.",
    );
    expect(LIVE_REFRESH_UNAVAILABLE_NOTICE).toBe(
      "Live sources could not be refreshed",
    );
  });

  it("renders official provenance before content with evidence metadata", () => {
    render(
      <KnowledgeModeSection
        banner={{
          id: "official",
          mode: "grounded_regulatory",
          confidence: "High",
          sourceCount: 6,
          updatedAt: "18 Jul 2026",
        }}
      >
        <p>Supported official summary.</p>
      </KnowledgeModeSection>,
    );

    const section = screen.getByRole("region", {
      name: "Official Regulatory Corpus section",
    });
    expect(
      within(section).getByText("Official Regulatory Corpus"),
    ).toBeInTheDocument();
    expect(
      within(section).getByText(
        "High confidence · 6 official sources · Updated 18 Jul 2026",
      ),
    ).toBeInTheDocument();
    expect(section.firstElementChild).toHaveAttribute(
      "data-mode",
      "grounded_regulatory",
    );
  });

  it("puts the exact healthy-no-match disclosure above Mode 2 prose", () => {
    render(
      <KnowledgeModeSection
        banner={{
          id: "general",
          mode: "general_ai",
          confidence: "Medium",
          trigger: "healthy_official_no_match",
        }}
        manualSearchHref="/browse"
      >
        <p>General orientation.</p>
      </KnowledgeModeSection>,
    );

    const section = screen.getByRole("region", {
      name: "General AI Knowledge section",
    });
    const paragraphs = section.querySelectorAll("p");
    expect(paragraphs[0]).toHaveTextContent(NO_OFFICIAL_DOCUMENTS_DISCLOSURE);
    expect(paragraphs[1]).toHaveTextContent("General orientation.");
    expect(
      within(section).getByText(
        "Medium confidence · No official corpus evidence found",
      ),
    ).toBeInTheDocument();
    expect(
      within(section).getByRole("link", {
        name: "Search official documents manually",
      }),
    ).toHaveAttribute("href", "/browse");
  });

  it("uses different exact copy for official retrieval outage", () => {
    render(
      <KnowledgeModeSection
        banner={{
          id: "general-outage",
          mode: "general_ai",
          confidence: "Low",
          trigger: "official_retrieval_unavailable",
          state: "degraded",
        }}
        manualSearchHref="/browse"
      />,
    );

    expect(
      screen.getByText(OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(NO_OFFICIAL_DOCUMENTS_DISCLOSURE),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Low confidence · Official verification unavailable"),
    ).toBeInTheDocument();
  });

  it("does not invent a no-documents disclosure for explicit general use", () => {
    const { container } = render(
      <GeneralAiDisclosure trigger="explicit_general_question" />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders live provenance with retrieval time before live content", () => {
    render(
      <KnowledgeModeSection
        banner={{
          id: "live",
          mode: "live_intelligence",
          confidence: "Medium",
          sourceCount: 4,
          retrievedAt: "26 Jul 2026, 14:32 IST",
        }}
      >
        <p>Current reporting.</p>
      </KnowledgeModeSection>,
    );

    const section = screen.getByRole("region", {
      name: "Live Web Sources section",
    });
    expect(
      within(section).getByText(
        "Time-sensitive · 4 sources · Retrieved 26 Jul 2026, 14:32 IST",
      ),
    ).toBeInTheDocument();
    expect(section.firstElementChild).toHaveAttribute(
      "data-mode",
      "live_intelligence",
    );
  });

  it("keeps official, live, and general sections as separate landmarks", () => {
    render(
      <>
        <KnowledgeModeSection
          banner={{
            id: "official",
            mode: "grounded_regulatory",
            confidence: "High",
            sourceCount: 1,
          }}
        />
        <KnowledgeModeSection
          banner={{
            id: "live",
            mode: "live_intelligence",
            confidence: "Medium",
            sourceCount: 1,
            retrievedAt: "27 Jul 2026, 10:00 IST",
          }}
        />
        <KnowledgeModeSection
          banner={{
            id: "general",
            mode: "general_ai",
            confidence: "Medium",
            trigger: "optional_general_background",
          }}
        />
      </>,
    );

    expect(screen.getAllByRole("region")).toHaveLength(3);
    expect(
      screen.getByRole("region", {
        name: "Official Regulatory Corpus section",
      }),
    ).toHaveAttribute("class", "ask-mode-section");
    expect(
      screen.getByRole("region", { name: "Live Web Sources section" }),
    ).not.toContainElement(
      screen.getByRole("region", {
        name: "Official Regulatory Corpus section",
      }),
    );
  });

  it("renders an attributed and keyboard-reachable live source card", async () => {
    const user = userEvent.setup();
    const { container } = render(
      <LiveSourceCard
        title="Consultation window extended"
        publisher="Central Electricity Regulatory Commission"
        sourceType="Official live notice"
        href="https://cerc.example/notices/123"
        publishedAt="2026-07-26T08:00:00+05:30"
        publishedLabel="26 Jul 2026, 08:00 IST"
        retrievedAt="2026-07-27T10:15:00+05:30"
        retrievedLabel="27 Jul 2026, 10:15 IST"
        coverageNote="Current reporting for the selected consultation."
      />,
    );

    const card = screen.getByRole("article");
    expect(
      within(card).getByText("Central Electricity Regulatory Commission"),
    ).toBeInTheDocument();
    expect(within(card).getByText("Official live notice")).toBeInTheDocument();
    expect(
      within(card).getByText(
        "Live reporting does not establish official legal status.",
      ),
    ).toBeInTheDocument();
    const times = container.querySelectorAll("time");
    expect(times[0]).toHaveAttribute(
      "datetime",
      "2026-07-26T08:00:00+05:30",
    );
    expect(times[1]).toHaveAttribute(
      "datetime",
      "2026-07-27T10:15:00+05:30",
    );

    const link = screen.getByRole("link", { name: "Open live source" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", "noreferrer");
    await user.tab();
    expect(link).toHaveFocus();
  });

  it("renders truthful empty and degraded live states as quiet status", () => {
    render(
      <>
        <ModeStatePanel kind="no_verified_live_updates" />
        <ModeStatePanel kind="live_refresh_unavailable" />
      </>,
    );

    expect(screen.getAllByRole("status")).toHaveLength(2);
    expect(screen.getByText(NO_VERIFIED_LIVE_UPDATES_NOTICE)).toBeInTheDocument();
    expect(screen.getByText(LIVE_REFRESH_UNAVAILABLE_NOTICE)).toBeInTheDocument();
    expect(
      screen.getByText(
        "Internal Regulatory Corpus research remains available.",
      ),
    ).toBeInTheDocument();
  });

  it("never turns an official outage into a healthy no-match claim", () => {
    render(
      <ModeStatePanel
        kind="official_search_unavailable"
        manualSearchHref="/browse"
      />,
    );

    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(OFFICIAL_SEARCH_UNAVAILABLE_DISCLOSURE);
    expect(status).not.toHaveTextContent(
      "no official regulatory documents were found",
    );
    expect(
      screen.getByRole("link", {
        name: "Search official documents manually",
      }),
    ).toHaveAttribute("href", "/browse");
  });

  it("announces pending official search without declaring an outcome", () => {
    render(<ModeStatePanel kind="official_search_pending" />);

    const status = screen.getByRole("status");
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(status).toHaveAttribute("aria-atomic", "true");
    expect(status).toHaveTextContent("Official evidence coverage is still being checked.");
    expect(status).not.toHaveTextContent("No official");
    expect(status).not.toHaveTextContent("unavailable");
  });

  it("keeps mode state on the banner without relying on color alone", () => {
    render(
      <KnowledgeModeBanner
        id="live-degraded"
        mode="live_intelligence"
        confidence="Low"
        sourceCount={1}
        retrievedAt="27 Jul 2026, 10:00 IST"
        state="degraded"
      />,
    );

    const heading = screen.getByText("Live Web Sources");
    expect(heading.closest("header")).toHaveAttribute("data-state", "degraded");
    expect(heading.closest("header")).toHaveAttribute(
      "data-mode",
      "live_intelligence",
    );
  });

  it("refuses dishonest counts and missing fallback actions", () => {
    expect(() =>
      render(
        <KnowledgeModeBanner
          id="bad-count"
          mode="grounded_regulatory"
          confidence="High"
          sourceCount={0}
        />,
      ),
    ).toThrow("positive source count");

    expect(() =>
      render(
        <KnowledgeModeSection
          banner={{
            id: "missing-action",
            mode: "general_ai",
            confidence: "Medium",
            trigger: "healthy_official_no_match",
          }}
        />,
      ),
    ).toThrow("requires manual document search");
  });

  it("refuses unsafe live links and timestamps without provenance timezone", () => {
    const common = {
      title: "Current report",
      publisher: "Publisher",
      sourceType: "Reporting",
      publishedLabel: "27 Jul 2026",
      retrievedLabel: "27 Jul 2026",
    };

    expect(() =>
      render(
        <LiveSourceCard
          {...common}
          href="javascript:alert(1)"
          publishedAt="2026-07-27T10:00:00+05:30"
          retrievedAt="2026-07-27T10:05:00+05:30"
        />,
      ),
    ).toThrow("HTTP(S) or application path");

    expect(() =>
      render(
        <LiveSourceCard
          {...common}
          href="https://live.example/report"
          publishedAt="2026-07-27T10:00:00"
          retrievedAt="2026-07-27T10:05:00+05:30"
        />,
      ),
    ).toThrow("timezone-aware");
  });
});
