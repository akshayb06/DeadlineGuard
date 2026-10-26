import time
from collections import defaultdict, deque
from threading import Lock


class SlidingWindowLimiter:
    """Allow at most max_requests per key in the last window_seconds."""

    def __init__(self, max_requests, window_seconds):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.hits = defaultdict(deque)  # key -> timestamps of recent allowed requests
        self.lock = Lock()

    def allow(self, key, now=None):
        with self.lock:
            return self._allow_locked(key,now)

    def _allow_locked(self,key,now=None):
        if now is None:
            now = time.monotonic()
        recent = self.hits[key]
        while recent and now - recent[0] >= self.window_seconds:
            recent.popleft()  # forget requests older than the window
        if len(recent) >= self.max_requests:
            retry_after = int(self.window_seconds - (now - recent[0])) + 1
            return False, retry_after
        recent.append(now)
        return True, 0


# PROPOSED: only creating a new session is rate limited this strictly
session_limiter = SlidingWindowLimiter(max_requests=3, window_seconds=60)
# BASELINE: every request (start, chunk, status, finalize) shares this counter
naive_limiter = SlidingWindowLimiter(max_requests=30, window_seconds=60)
transfer_limiter = SlidingWindowLimiter(max_requests=240, window_seconds=60)

MODE = {"value": "session_aware"}  # or "naive"


def check_rate_limit(user_id, kind):
    """kind: 'new_session' or 'other'. Returns (allowed, retry_after_seconds)."""
    if MODE["value"] == "naive":
        return naive_limiter.allow(user_id)
    if kind == "new_session":
        return session_limiter.allow(user_id)
    return transfer_limiter.allow(user_id)  # separate continuation budget


def reset():
    session_limiter.hits.clear()
    naive_limiter.hits.clear()
    transfer_limiter.hits.clear()
