import { describe, expect, it } from "vitest";

import { patchDigestEvents, patchEventBookmark } from "./bookmarks";

describe("bookmark cache helpers", () => {
  it("updates bookmark state on a matching event and leaves others unchanged", () => {
    const events = [
      { id: 1, is_bookmarked: false },
      { id: 2, is_bookmarked: true },
    ];

    expect(patchEventBookmark(events, 1, true)).toEqual([
      { id: 1, is_bookmarked: true },
      { id: 2, is_bookmarked: true },
    ]);
    expect(events[0].is_bookmarked).toBe(false);
  });

  it("patches digest events in place without dropping the rest of the payload", () => {
    const digest = {
      digest_date: "2026-08-18",
      event_count: 1,
      events: [{ id: 9, is_bookmarked: false }],
    };

    expect(patchDigestEvents(digest, 9, true)).toEqual({
      digest_date: "2026-08-18",
      event_count: 1,
      events: [{ id: 9, is_bookmarked: true }],
    });
  });
});
