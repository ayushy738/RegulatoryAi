export type Bookmarkable = {
  id: number;
  is_bookmarked: boolean;
};

export function patchEventBookmark<T extends Bookmarkable>(
  items: T[],
  eventId: number,
  isBookmarked: boolean,
): T[] {
  return items.map((item) =>
    item.id === eventId ? { ...item, is_bookmarked: isBookmarked } : item,
  );
}

export function patchDigestEvents<T extends { events: Bookmarkable[] }>(
  digest: T,
  eventId: number,
  isBookmarked: boolean,
): T {
  return {
    ...digest,
    events: patchEventBookmark(digest.events, eventId, isBookmarked),
  };
}
