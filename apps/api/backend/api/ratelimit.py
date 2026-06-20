from collections import defaultdict, deque
from time import monotonic

from fastapi import HTTPException, Request, status


class TokenBucket:
    def __init__(self, limit: int, window_s: int) -> None:
        self.limit = limit
        self.window_s = window_s
        self.events: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str) -> None:
        now = monotonic()
        window_start = now - self.window_s
        bucket = self.events[key]
        while bucket and bucket[0] < window_start:
            bucket.popleft()
        if len(bucket) >= self.limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded",
            )
        bucket.append(now)


chat_bucket = TokenBucket(limit=30, window_s=60)


async def limit_chat(request: Request) -> None:
    forwarded = request.headers.get("x-forwarded-for")
    key = forwarded.split(",", 1)[0].strip() if forwarded else request.client.host
    chat_bucket.check(key or "anonymous")
