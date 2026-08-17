import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { AdminSourcesView } from "@/app/features/admin/AdminSourcesView";

const deleteSourcePage = vi.fn();
const restoreSourcePage = vi.fn();
const permanentlyDeleteSourcePage = vi.fn();
const getSourcePagesForSource = vi.fn();
const getAdminSources = vi.fn();
const setStatusMessage = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    deleteSourcePage: (...args: unknown[]) => deleteSourcePage(...args),
    restoreSourcePage: (...args: unknown[]) => restoreSourcePage(...args),
    permanentlyDeleteSourcePage: (...args: unknown[]) =>
      permanentlyDeleteSourcePage(...args),
    getSourcePagesForSource: (...args: unknown[]) => getSourcePagesForSource(...args),
    getAdminSources: (...args: unknown[]) => getAdminSources(...args),
    createSourcePage: vi.fn(),
    createSource: vi.fn(),
    deleteSource: vi.fn(),
    updateSourcePage: vi.fn(),
  };
});

vi.mock("@/app/workspace/WorkspaceContext", () => ({
  useWorkspace: () => ({
    busyAction: null,
    token: "test-token",
    setStatusMessage,
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

const retiredPage = {
  id: 84,
  source_id: 42,
  source_code: "GERC",
  name: "Draft Regulations",
  url: "https://gercin.org/regulations/draft_regulations",
  page_type: "listing",
  priority: 30,
  enabled: true,
  last_crawled_at: null,
  deleted_at: "2026-08-17T12:00:00Z",
  deleted_by: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
};

/**
 * The retired list is fetched with include_retired=true; the active list is
 * fetched without it. Both go through the same endpoint, so the mock answers
 * per call shape rather than per call order.
 */
function mockPages({ retired = [] as unknown[] } = {}) {
  getSourcePagesForSource.mockImplementation(
    (_sourceId: number, _token: string, includeRetired?: boolean) =>
      Promise.resolve(includeRetired ? [activePage, ...retired] : [activePage]),
  );
}

async function expandSource(user: ReturnType<typeof userEvent.setup>) {
  await user.click(
    await screen.findByRole("button", {
      name: /expand gujarat electricity regulatory commission/i,
    }),
  );
}

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

describe("AdminSourcesView soft delete", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  beforeEach(() => {
    getAdminSources.mockResolvedValue({
      items: [source],
      total: 1,
      page: 1,
      page_size: 12,
      total_pages: 1,
    });
  });

  it("offers a reversible Remove for active pages, never permanent delete", async () => {
    mockPages();

    const user = userEvent.setup();
    renderView();
    await expandSource(user);

    await user.click(
      await screen.findByRole("button", {
        name: /more actions for orders on renewable energy/i,
      }),
    );
    const menu = screen.getByRole("menu");
    expect(within(menu).getByRole("menuitem", { name: /^remove$/i })).toBeInTheDocument();
    expect(
      within(menu).queryByRole("menuitem", { name: /permanently delete/i }),
    ).not.toBeInTheDocument();

    await user.click(within(menu).getByRole("menuitem", { name: /^remove$/i }));

    const dialog = await screen.findByRole("dialog", {
      name: /remove this page from monitoring/i,
    });
    expect(within(dialog).getByText(/you can restore it later/i)).toBeInTheDocument();
    expect(deleteSourcePage).not.toHaveBeenCalled();
  });

  it("retires the page after the remove confirmation", async () => {
    mockPages();
    deleteSourcePage.mockResolvedValue({
      page_id: 1,
      source_id: 42,
      deleted: true,
      retired: true,
    });

    const user = userEvent.setup();
    renderView();
    await expandSource(user);

    await user.click(
      await screen.findByRole("button", {
        name: /more actions for orders on renewable energy/i,
      }),
    );
    await user.click(screen.getByRole("menuitem", { name: /^remove$/i }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: /^remove page$/i,
      }),
    );

    expect(deleteSourcePage).toHaveBeenCalledWith(1, "test-token");
    expect(setStatusMessage).toHaveBeenCalledWith(expect.stringMatching(/preserved/i));
  });

  it("lists retired pages with restore and permanent delete", async () => {
    mockPages({ retired: [retiredPage] });
    restoreSourcePage.mockResolvedValue({
      page_id: 84,
      source_id: 42,
      restored: true,
      page: { id: 84, deleted_at: null },
    });

    const user = userEvent.setup();
    renderView();
    await expandSource(user);
    await user.click(await screen.findByText(/show retired pages/i));

    const retiredTitle = await screen.findByText("Draft Regulations");
    const retiredRow = retiredTitle.closest(".rv-page-row") as HTMLElement;
    expect(within(retiredRow).getByText(/^retired$/i)).toBeInTheDocument();
    expect(getSourcePagesForSource).toHaveBeenCalledWith(42, "test-token", true);

    await user.click(within(retiredRow).getByRole("button", { name: /^restore$/i }));
    expect(restoreSourcePage).toHaveBeenCalledWith(84, "test-token");
  });

  it("requires a second confirmation before permanent delete", async () => {
    mockPages({ retired: [retiredPage] });
    permanentlyDeleteSourcePage.mockResolvedValue({
      page_id: 84,
      source_id: 42,
      deleted: true,
    });

    const user = userEvent.setup();
    renderView();
    await expandSource(user);
    await user.click(await screen.findByText(/show retired pages/i));

    const retiredRow = (await screen.findByText("Draft Regulations")).closest(
      ".rv-page-row",
    ) as HTMLElement;
    await user.click(
      within(retiredRow).getByRole("button", {
        name: /more actions for retired page draft regulations/i,
      }),
    );
    await user.click(screen.getByRole("menuitem", { name: /permanently delete/i }));

    expect(permanentlyDeleteSourcePage).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog", {
      name: /permanently delete this source page/i,
    });
    expect(
      within(dialog).getByText(/does not delete regulatory documents/i),
    ).toBeInTheDocument();

    await user.click(
      within(dialog).getByRole("button", { name: /^permanently delete$/i }),
    );
    expect(permanentlyDeleteSourcePage).toHaveBeenCalledWith(84, "test-token");
    expect(setStatusMessage).toHaveBeenCalledWith(
      expect.stringMatching(/permanently deleted/i),
    );
  });

  it("surfaces permanent delete failures as a status message", async () => {
    mockPages({ retired: [retiredPage] });
    permanentlyDeleteSourcePage.mockRejectedValue(
      new Error("Only retired source pages can be permanently deleted."),
    );

    const user = userEvent.setup();
    renderView();
    await expandSource(user);
    await user.click(await screen.findByText(/show retired pages/i));

    const retiredRow = (await screen.findByText("Draft Regulations")).closest(
      ".rv-page-row",
    ) as HTMLElement;
    await user.click(
      within(retiredRow).getByRole("button", {
        name: /more actions for retired page draft regulations/i,
      }),
    );
    await user.click(screen.getByRole("menuitem", { name: /permanently delete/i }));
    await user.click(
      within(await screen.findByRole("dialog")).getByRole("button", {
        name: /^permanently delete$/i,
      }),
    );

    expect(setStatusMessage).toHaveBeenCalledWith(
      "Only retired source pages can be permanently deleted.",
    );
  });

  it("explains the retired list when it is empty", async () => {
    mockPages();

    const user = userEvent.setup();
    renderView();
    await expandSource(user);
    await user.click(await screen.findByText(/show retired pages/i));

    expect(await screen.findByText(/no retired pages/i)).toBeInTheDocument();
    expect(
      screen.getByText(/pages you remove from monitoring will appear here/i),
    ).toBeInTheDocument();
  });
});
