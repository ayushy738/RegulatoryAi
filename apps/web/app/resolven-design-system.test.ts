import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

const appRoot = resolve(import.meta.dirname);
const globalCss = readFileSync(resolve(appRoot, "globals.css"), "utf8");
const designCss = readFileSync(
  resolve(appRoot, "resolven-design-system.css"),
  "utf8",
);
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
});
