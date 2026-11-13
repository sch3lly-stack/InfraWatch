"""Small in-process sliding-window rate limiter (per key). For multi-replica
deployments put a shared limiter (e.g. reverse proxy) in front."""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException


class RateLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, limit: int, window: float = 60.0) -> None:
        if limit <= 0:
            return
        now = time.monotonic()
        with self._lock:
            q = self._hits[key]
            while q and now - q[0] > window:
                q.popleft()
            if len(q) >= limit:
                retry = max(1, int(window - (now - q[0])))
                raise HTTPException(429, "rate limit exceeded", headers={"Retry-After": str(retry)})
            q.append(now)
            if len(self._hits) > 20000:  # bound memory
                for k in [k for k, v in self._hits.items() if not v or now - v[-1] > window]:
                    del self._hits[k]

    def reset(self) -> None:
        with self._lock:
            self._hits.clear()
