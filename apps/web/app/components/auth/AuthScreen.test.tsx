import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuthScreen } from "./AuthScreen";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AuthScreen", () => {
  it("renders the workspace sign-in surface rather than the marketing purple canvas", () => {
    render(
      <AuthScreen
        email=""
        password=""
        message=""
        loading={false}
        onEmail={() => undefined}
        onPassword={() => undefined}
        onSignIn={async () => undefined}
      />,
    );

    const surface = document.querySelector("main.auth-signin-screen");
    expect(surface).not.toBeNull();
    expect(surface).toHaveClass("auth-premium-screen");
    expect(screen.getByRole("heading", { name: "Sign in" })).toBeInTheDocument();
  });
});
