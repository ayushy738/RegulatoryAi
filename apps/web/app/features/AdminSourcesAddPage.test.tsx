import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminSourcesView } from "@/app/features/admin/AdminSourcesView";

const getAdminSources = vi.fn();
const getSourcePagesForSource = vi.fn();
const createSourcePage = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    getAdminSources: (...args: unknown[]) => getAdminSources(...args),
    getSourcePagesForSource: (...args: unknown[]) => getSourcePagesForSource(...args),
    createSourcePage: (...args: unknown[]) => createSourcePage(...args),
    updateSourcePage: vi.fn(),
    deleteSource: vi.fn(),
    createSource: vi.fn(),
  };
});

vi.mock("@/app/workspace/WorkspaceContext", () => ({
  useWorkspace: () => ({
    busyAction: null,
    token: "test-token",
    setStatusMessage: vi.fn(),
    handleToggleSource: vi.fn(),
    handleSourceCrawl: vi.fn(),
    handlePageCrawl: vi.fn(),
  }),
}));

const source = {
  id: 42,
  code: "GERC",
  name: "Gujarat Electricity Regulatory Commission",
  jurisdiction: "state",
  crawler_type: "agent",
  url: "https://gercin.org/",
  allowed_domains: ["gercin.org"],
  enabled: true,
  consecutive_failures: 0,
  last_checked_at: null,
  last_status: null,
  page_count: 1,
  enabled_page_count: 1,
};

const activePage = {
  id: 1,
  source_id: 42,
  source_code: "GERC",
  name: "Orders on Renewable Energy",
  url: "https://gercin.org/orders/orders_renewable_energy",
  page_type: "listing",
  priority: 10,
  enabled: true,
  last_crawled_at: null,
  deleted_at: null,
  deleted_by: null,
};

function renderView() {
  const client = new QueryClient({
    defaultOptions: { mutations: { retry: false }, queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AdminSourcesView />
    </QueryClientProvider>,
  );
}

describe("AdminSourcesView add page", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("offers Add page on an existing source and opens the page modal", async () => {
    getAdminSources.mockResolvedValue({
      items: [source],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    getSourcePagesForSource.mockResolvedValue([activePage]);

    const user = userEvent.setup();
    renderView();

    await user.click(
      await screen.findByRole("button", {
        name: /expand gujarat electricity regulatory commission/i,
      }),
    );

    const addButton = await screen.findByRole("button", { name: /^add page$/i });
    await user.click(addButton);

    const dialog = await screen.findByRole("dialog", { name: /add monitored page/i });
    expect(dialog).toBeInTheDocument();
    expect(screen.getByPlaceholderText("Draft Regulations")).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/example\.gov\.in\/regulations\/draft/i),
    ).toBeInTheDocument();
  });

  it("submits the new page through the existing source-page endpoint", async () => {
    getAdminSources.mockResolvedValue({
      items: [source],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    getSourcePagesForSource.mockResolvedValue([activePage]);
    createSourcePage.mockResolvedValue({ ...activePage, id: 2, name: "Draft Regulations" });

    const user = userEvent.setup();
    renderView();

    await user.click(
      await screen.findByRole("button", {
        name: /expand gujarat electricity regulatory commission/i,
      }),
    );
    await user.click(await screen.findByRole("button", { name: /^add page$/i }));

    await user.type(screen.getByPlaceholderText("Draft Regulations"), "Draft Regulations");
    await user.type(
      screen.getByPlaceholderText(/example\.gov\.in\/regulations\/draft/i),
      "https://gercin.org/regulations/draft",
    );

    const dialog = screen.getByRole("dialog", { name: /add monitored page/i });
    await user.click(
      within(dialog).getByRole("button", { name: /^add page$/i }),
    );

    expect(createSourcePage).toHaveBeenCalledWith(
      42,
      expect.objectContaining({
        name: "Draft Regulations",
        url: "https://gercin.org/regulations/draft",
      }),
      "test-token",
    );
  });

  it("blocks submission with an inline error when the URL is missing", async () => {
    getAdminSources.mockResolvedValue({
      items: [source],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
    getSourcePagesForSource.mockResolvedValue([activePage]);

    const user = userEvent.setup();
    renderView();

    await user.click(
      await screen.findByRole("button", {
        name: /expand gujarat electricity regulatory commission/i,
      }),
    );
    await user.click(await screen.findByRole("button", { name: /^add page$/i }));

    const dialog = screen.getByRole("dialog", { name: /add monitored page/i });
    await user.type(screen.getByPlaceholderText("Draft Regulations"), "Draft Regulations");
    await user.click(within(dialog).getByRole("button", { name: /^add page$/i }));

    expect(createSourcePage).not.toHaveBeenCalled();
    expect(within(dialog).getByRole("alert")).toBeInTheDocument();
  });
});
