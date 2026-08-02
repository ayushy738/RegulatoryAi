import { describe, expect, it } from "vitest";

import {
  parseFeatureFlag,
  resolveAskAiV2UiEnabled,
} from "./ask-ai-flags";

describe("Ask AI public flags", () => {
  it("defaults the v2 UI off", () => {
    expect(resolveAskAiV2UiEnabled({})).toBe(false);
  });

  it.each(["true", " TRUE "])("accepts the explicit true value %j", (value) => {
    expect(parseFeatureFlag(value)).toBe(true);
  });

  it.each(["false", "1", "yes", "on", "", "unexpected"])(
    "fails closed for %j",
    (value) => {
      expect(parseFeatureFlag(value)).toBe(false);
    },
  );

  it("prefers the Next public value over the Vite compatibility value", () => {
    expect(
      resolveAskAiV2UiEnabled({
        NEXT_PUBLIC_ASK_AI_V2_UI_ENABLED: "false",
        VITE_ASK_AI_V2_UI_ENABLED: "true",
      }),
    ).toBe(false);
  });
});
