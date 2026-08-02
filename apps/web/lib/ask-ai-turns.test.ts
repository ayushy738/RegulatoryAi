import { describe, expect, it } from "vitest";

import turnContract from "../../api/backend/tests/fixtures/ask_turn_contract.json";
import { askMessageSchema, askTurnListSchema } from "./ask-ai-turns";

describe("Ask AI turn contracts", () => {
  it("parses the backend's recorded message response", () => {
    expect(askMessageSchema.parse(turnContract.message_response)).toEqual(
      turnContract.message_response,
    );
  });

  it("parses the backend's complete recorded turn response", () => {
    expect(askTurnListSchema.parse(turnContract.turn_list_response)).toEqual(
      turnContract.turn_list_response,
    );
  });
});
