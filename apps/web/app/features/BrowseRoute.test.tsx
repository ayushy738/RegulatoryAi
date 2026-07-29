import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RouteView } from "./RouteView";

const routeFixture = vi.hoisted(() => ({
  state: {
    route: "browse",
    v2AskEnabled: false,
  },
}));

vi.mock("@/app/workspace/WorkspaceContext", () => ({
  useWorkspace: () => routeFixture.state,
}));

vi.mock("./LatestView", () => ({
  LatestView: () => <div>legacy-latest-view</div>,
}));

vi.mock("./ManualDocumentSearchRoute", () => ({
  ManualDocumentSearchRoute: () => <div>manual-document-search</div>,
}));

afterEach(cleanup);

describe("Browse route feature boundary", () => {
  it("preserves the legacy latest view while the v2 flag is off", () => {
    routeFixture.state.v2AskEnabled = false;
    render(<RouteView />);

    expect(screen.getByText("legacy-latest-view")).toBeInTheDocument();
    expect(
      screen.queryByText("manual-document-search"),
    ).not.toBeInTheDocument();
  });

  it("mounts manual document search only while the v2 flag is on", () => {
    routeFixture.state.v2AskEnabled = true;
    render(<RouteView />);

    expect(screen.getByText("manual-document-search")).toBeInTheDocument();
    expect(screen.queryByText("legacy-latest-view")).not.toBeInTheDocument();
  });
});
