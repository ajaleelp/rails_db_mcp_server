"""Simple in-memory rate limiter."""

from __future__ import annotations

import time
from collections import deque


class RateLimitExceeded(Exception):
    """Raised when too many requests are made within the window."""


class RateLimiter:
    WINDOW_SECONDS = 60

    def __init__(self, requests_per_minute: int) -> None:
        self.requests_per_minute = max(1, requests_per_minute)
        self._events: deque[float] = deque()

    def check_and_record(self) -> None:
        now = time.monotonic()
        window_start = now - self.WINDOW_SECONDS
        while self._events and self._events[0] < window_start:
            self._events.popleft()
        if len(self._events) >= self.requests_per_minute:
            raise RateLimitExceeded("Rate limit exceeded")
        self._events.append(now)
