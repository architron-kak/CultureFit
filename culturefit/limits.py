"""Process-local request limits and an outbound LLM budget. No background tasks."""
from collections import deque
from math import ceil
from threading import Lock
import time


class RequestLimiter:
    """Rolling window keyed by (endpoint, IP); rejected attempts do not extend it."""

    def __init__(self, window=3600, clock=time.monotonic):
        self.window = window
        self.clock = clock
        self._requests = {}
        self._lock = Lock()

    def retry_after(self, key, limit):
        """Consume a slot, or return the seconds until one becomes available."""
        with self._lock:
            now = self.clock()
            # Drop inactive IPs as well as old timestamps to bound idle state.
            for stored_key, timestamps in list(self._requests.items()):
                while timestamps and timestamps[0] <= now - self.window:
                    timestamps.popleft()
                if not timestamps:
                    del self._requests[stored_key]
            timestamps = self._requests.setdefault(key, deque())
            if len(timestamps) >= limit:
                return max(1, ceil(timestamps[0] + self.window - now))
            timestamps.append(now)
            return 0


class DailyBudget:
    """Reserve outbound attempts before awaiting I/O; reset at midnight UTC."""

    def __init__(self, limit=150, clock=time.time):
        self.limit = limit
        self.clock = clock
        self._day = None
        self._used = 0
        self._lock = Lock()

    def take(self):
        with self._lock:
            day = int(self.clock() // 86400)
            if day != self._day:
                self._day, self._used = day, 0
            if self._used >= self.limit:
                return False
            self._used += 1
            return True
