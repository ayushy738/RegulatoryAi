import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  manualDocumentSearchFixture,
} from "../../../test/manual-document-search-fixture";

import { ManualDocumentSearch } from "./ManualDocumentSearch";

const searchFixture = vi.hoisted(() => ({
  state: {
    available: true,
    isPending: false,
    mutateAsync: vi.fn(),
  },
}));

vi.mock("@/lib/ask-ai-data", () => ({
  useManualDocumentSearch: () => searchFixture.state,
}));

beforeEach(() => {
  searchFixture.state.available = true;
  searchFixture.state.isPending = false;
  searchFixture.state.mutateAsync.mockReset();
  window.history.replaceState({}, "", "/browse");
});

afterEach(cleanup);

describe("ManualDocumentSearch", () => {
  it("submits every exact filter and renders official metadata and excerpts", async () => {
    const user = userEvent.setup();
    searchFixture.state.mutateAsync.mockResolvedValue(
      manualDocumentSearchFixture(),
    );
    render(<ManualDocumentSearch />);

    await user.type(screen.getByLabelText("Search terms"), "deviation charge");
    await user.click(screen.getByLabelText("Match exact phrase"));
    await user.type(screen.getByLabelText("Title"), "DSM Regulations");
    await user.type(screen.getByLabelText("Issuer"), "CERC");
    await user.type(
      screen.getByLabelText("Document number"),
      "CERC/DSM/2026",
    );
    await user.type(screen.getByLabelText("Document type"), "REGULATION");
    await user.type(screen.getByLabelText("Family"), "DSM family");
    await user.type(screen.getByLabelText("Version"), "Version 2");
    await user.selectOptions(
      screen.getByLabelText("Current status"),
      "current",
    );
    await user.type(
      screen.getByLabelText("Within-document text"),
      "generators",
    );
    await user.type(screen.getByLabelText("Issued from"), "2026-01-01");
    await user.type(screen.getByLabelText("Effective to"), "2026-12-31");
    await user.click(
      screen.getByRole("button", { name: "Search official documents" }),
    );

    expect(searchFixture.state.mutateAsync).toHaveBeenCalledWith({
      schema_version: "1",
      query: "deviation charge",
      exact_phrase: true,
      title: "DSM Regulations",
      issuer: "CERC",
      document_number: "CERC/DSM/2026",
      document_type: "REGULATION",
      family: "DSM family",
      version: "Version 2",
      status: "current",
      issued_from: "2026-01-01",
      issued_to: undefined,
      effective_from: undefined,
      effective_to: "2026-12-31",
      within_document: "generators",
      limit: 20,
    });
    expect(
      await screen.findByRole("heading", { name: "DSM Regulations 2026" }),
    ).toBeInTheDocument();
    expect(screen.getByText("CERC/DSM/2026")).toBeInTheDocument();
    expect(
      screen.getByText(/deviation charge applies to interstate generators/i),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: "Open official source" }),
    ).toHaveAttribute("href", "https://example.test/dsm");
  });

  it("restores canonical document identity and sends opaque pagination", async () => {
    const user = userEvent.setup();
    window.history.replaceState(
      {},
      "",
      "/browse?document=10&version=20",
    );
    const firstPage = manualDocumentSearchFixture();
    const secondPage = manualDocumentSearchFixture();
    secondPage.items = secondPage.items.map((item) => ({
      ...item,
      result_id: "document:11:21",
      document_id: 11,
      registry_version_id: 21,
      title: "DSM Procedures 2026",
      route: "/browse?document=11&version=21",
    }));
    secondPage.next_cursor = null;
    searchFixture.state.mutateAsync
      .mockResolvedValueOnce(firstPage)
      .mockResolvedValueOnce(secondPage);

    render(<ManualDocumentSearch />);

    await waitFor(() =>
      expect(searchFixture.state.mutateAsync).toHaveBeenCalledWith({
        schema_version: "1",
        document_id: 10,
        registry_version_id: 20,
        exact_phrase: false,
        limit: 20,
      }),
    );
    await user.click(
      await screen.findByRole("button", {
        name: "Load more exact results",
      }),
    );
    await waitFor(() =>
      expect(searchFixture.state.mutateAsync).toHaveBeenLastCalledWith({
        schema_version: "1",
        document_id: 10,
        registry_version_id: 20,
        exact_phrase: false,
        cursor: "next-manual-page",
        limit: 20,
      }),
    );
    expect(
      await screen.findByRole("heading", { name: "DSM Procedures 2026" }),
    ).toBeInTheDocument();
  });

  it("restores a historical version route without a document parameter", async () => {
    window.history.replaceState({}, "", "/browse?version=20");
    searchFixture.state.mutateAsync.mockResolvedValue(
      manualDocumentSearchFixture(),
    );

    render(<ManualDocumentSearch />);

    await waitFor(() =>
      expect(searchFixture.state.mutateAsync).toHaveBeenCalledWith({
        schema_version: "1",
        document_id: undefined,
        registry_version_id: 20,
        exact_phrase: false,
        limit: 20,
      }),
    );
  });

  it("keeps no-match, unavailable, and disabled states explicit and safe", async () => {
    const user = userEvent.setup();
    searchFixture.state.mutateAsync.mockResolvedValueOnce({
      ...manualDocumentSearchFixture(),
      status: "no_match",
      items: [],
      next_cursor: null,
    });
    render(<ManualDocumentSearch />);

    await user.type(screen.getByLabelText("Title"), "unknown");
    await user.click(
      screen.getByRole("button", { name: "Search official documents" }),
    );
    expect(
      await screen.findByText(/No official document matched/),
    ).toBeInTheDocument();

    searchFixture.state.mutateAsync.mockRejectedValueOnce(
      new Error("raw database detail"),
    );
    await user.click(
      screen.getByRole("button", { name: "Search official documents" }),
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "temporarily unavailable",
    );
    expect(screen.queryByText("raw database detail")).not.toBeInTheDocument();

    cleanup();
    searchFixture.state.available = false;
    render(<ManualDocumentSearch />);
    expect(
      screen.getByRole("button", { name: "Search official documents" }),
    ).toBeDisabled();
    expect(screen.getByRole("alert")).toHaveTextContent(
      "not enabled in this rollout",
    );
  });
});
