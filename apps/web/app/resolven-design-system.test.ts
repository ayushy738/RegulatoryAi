import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const appRoot = resolve(import.meta.dirname);

/** Line endings depend on the checkout, so assertions compare on LF only. */
function readCss(name: string) {
  return readFileSync(resolve(appRoot, name), "utf8").replaceAll("\r\n", "\n");
}

const globalCss = readCss("globals.css");
const designCss = readCss("resolven-design-system.css");
const uiCss = readCss("resolven-ui.css");
const rootLayout = readFileSync(resolve(appRoot, "layout.tsx"), "utf8");

describe("Resolven presentation design system", () => {
  it("uses the approved deck palette and typography tokens", () => {
    expect(globalCss).toContain("--brand-purple: #522b91");
    expect(globalCss).toContain("--brand-green: #3db769");
    expect(globalCss).toContain("--brand-lavender: #c8b6d8");
    expect(globalCss).toContain("--brand-lime: #9bcd72");
    expect(globalCss).toContain("--ink: #202020");
    expect(globalCss).toContain('"Verbatim Wide Bold Oblique"');
    expect(globalCss).toContain('"Verbatim Light"');
  });

  it("loads the shared visual layer after the legacy stylesheet", () => {
    expect(rootLayout.indexOf('import "./globals.css"')).toBeGreaterThan(-1);
    expect(
      rootLayout.indexOf('import "./resolven-design-system.css"'),
    ).toBeGreaterThan(rootLayout.indexOf('import "./globals.css"'));
  });

  it("defines shared focus, surface, workspace, state, and responsive rules", () => {
    expect(designCss).toContain(":focus-visible");
    expect(designCss).toContain(".product-topnav");
    expect(designCss).toContain(".panel,");
    expect(designCss).toContain(".research-workspace-shell");
    expect(designCss).toContain(".evidence-drawer");
    expect(designCss).toContain(".empty-state");
    expect(designCss).toContain("@media (max-width: 640px)");
    expect(designCss).toContain("@media (prefers-reduced-motion: reduce)");
  });

  it("keeps authentication surfaces legible and reachable across breakpoints", () => {
    expect(designCss).toContain(".auth-premium-brand h1");
    expect(designCss).toContain("color: #fff");
    expect(designCss).toContain(".auth-premium-brand .auth-eyebrow");
    expect(designCss).toContain("color: var(--brand-lime)");
    expect(designCss).toContain(".auth-visualization {\n    display: none;");
    expect(designCss).toContain(".auth-premium-panel {\n    padding: 22px 18px;");
  });

  it("renders login on a calm workspace background instead of a purple canvas", () => {
    expect(uiCss).toContain(".auth-signin-screen");
    expect(uiCss).toContain("background: transparent;");
    expect(uiCss).not.toMatch(
      /\.auth-signin-screen \{[\s\S]*linear-gradient\(135deg, rgba\(82, 43, 145/,
    );
    expect(uiCss).toContain(".rv-select {\n  display: inline-flex;");
    expect(uiCss).toContain("width: 12.5rem;");
    expect(uiCss).toContain(".rv-intel-card {\n  display: flex;");
    expect(uiCss).toContain("min-height: 17.5rem;");
    expect(uiCss).toContain(".rv-card--fill {\n  height: 100%;\n}");
  });
});
