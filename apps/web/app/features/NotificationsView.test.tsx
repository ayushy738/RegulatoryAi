import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { NotificationsView } from "@/app/features/NotificationsView";

const saveSpy = vi.fn();
const setSettingsSpy = vi.fn();

let settingsState = {
  jurisdictions: [] as string[],
  source_ids: [] as number[],
  topics: [] as string[],
  email_enabled: false,
  frequency: "instant" as const,
};

vi.mock("@/app/workspace/WorkspaceContext", () => ({
  useWorkspace: () => ({
    settings: settingsState,
    setSettings: (next: typeof settingsState) => {
      settingsState = next;
      setSettingsSpy(next);
    },
    catalogSources: [
      { id: 1, code: "cerc", name: "CERC", enabled: true },
      { id: 2, code: "mop", name: "Ministry of Power", enabled: true },
      { id: 3, code: "mnre", name: "MNRE", enabled: true },
    ],
    events: [],
    digestDate: "2026-08-16",
    busyAction: null,
    handleSaveSettings: saveSpy,
    subscriptionsStatus: { isLoading: false, isError: false, error: null, refetch: vi.fn() },
  }),
}));

describe("NotificationsView subscription preferences", () => {
  beforeEach(() => {
    settingsState = {
      jurisdictions: [],
      source_ids: [],
      topics: [],
      email_enabled: false,
      frequency: "instant",
    };
    saveSpy.mockReset();
    setSettingsSpy.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("enables email, selects one source, and saves instant preferences", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<NotificationsView />);

    await user.click(screen.getByLabelText("Email me regulatory updates"));
    expect(setSettingsSpy).toHaveBeenCalled();
    settingsState = { ...settingsState, email_enabled: true, frequency: "instant" };
    rerender(<NotificationsView />);

    await user.click(screen.getByLabelText("CERC"));
    expect(settingsState.source_ids).toEqual([2, 3]);

    settingsState = { ...settingsState, source_ids: [1], email_enabled: true };
    rerender(<NotificationsView />);
    await user.click(screen.getByRole("button", { name: /save preferences/i }));
    expect(saveSpy).toHaveBeenCalled();
    expect(screen.getByText(/Email notifications: ON/i)).toBeInTheDocument();
    expect(screen.getByText(/Sources: CERC/i)).toBeInTheDocument();
    expect(screen.getByText(/Frequency: Instant/i)).toBeInTheDocument();
  });

  it("persists all-sources semantics when All sources is selected", async () => {
    const user = userEvent.setup();
    settingsState = {
      ...settingsState,
      email_enabled: true,
      source_ids: [1, 2],
      frequency: "instant",
    };
    render(<NotificationsView />);
    const allSources = screen.getAllByRole("checkbox", { name: "All sources" })[0];
    await user.click(allSources);
    expect(setSettingsSpy).toHaveBeenCalledWith(
      expect.objectContaining({ source_ids: [], frequency: "instant" }),
    );
  });

  it("keeps multiple selected sources in local preference state", async () => {
    settingsState = {
      ...settingsState,
      email_enabled: true,
      source_ids: [1, 2],
      frequency: "instant",
    };
    render(<NotificationsView />);
    expect(screen.getByText(/Sources: CERC, Ministry of Power/i)).toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: "CERC" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Ministry of Power" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "MNRE" })).not.toBeChecked();
  });
});
