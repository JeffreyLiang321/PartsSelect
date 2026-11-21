"""
In-memory sliding-window rate limiter.

The API runs as a single container, so an in-process limiter is enough —
no Redis needed. Three layers:
  - per IP, per minute   (stops bursts / scripted loops)
  - per IP, per day      (stops one person draining the budget slowly)
  - global, per day      (backstop if someone rotates IPs)

Limits reset on restart, which is acceptable: the OpenAI project budget is
the hard ceiling behind all of this.
"""

import os
import threading
import time
from collections import defaultdict, deque

MINUTE = 60
DAY = 24 * 60 * 60


class RateLimiter:
    def __init__(self, per_ip_minute: int, per_ip_day: int, global_day: int):
        self.per_ip_minute = per_ip_minute
        self.per_ip_day = per_ip_day
        self.global_day = global_day

        self._ip_hits: dict[str, deque] = defaultdict(deque)  # timestamps, last 24h
        self._global_hits: deque = deque()
        self._lock = threading.Lock()

    @staticmethod
    def _prune(hits: deque, now: float, window: int) -> None:
        while hits and hits[0] <= now - window:
            hits.popleft()

    def check(self, ip: str) -> tuple[bool, int, str]:
        """
        Record a request from `ip` if it's within limits.
        Returns (allowed, retry_after_seconds, reason).
        """
        now = time.time()
        with self._lock:
            self._prune(self._global_hits, now, DAY)
            if len(self._global_hits) >= self.global_day:
                retry = int(self._global_hits[0] + DAY - now) + 1
                return False, retry, "global_daily"

            hits = self._ip_hits[ip]
            self._prune(hits, now, DAY)

            if len(hits) >= self.per_ip_day:
                return False, int(hits[0] + DAY - now) + 1, "ip_daily"

            recent = sum(1 for t in hits if t > now - MINUTE)
            if recent >= self.per_ip_minute:
                oldest_recent = next(t for t in hits if t > now - MINUTE)
                return False, int(oldest_recent + MINUTE - now) + 1, "ip_minute"

            hits.append(now)
            self._global_hits.append(now)

            # Drop IPs with no activity in the last day so the dict can't grow forever
            if len(self._ip_hits) > 2000:
                for key in [k for k, v in self._ip_hits.items() if not v or v[-1] <= now - DAY]:
                    del self._ip_hits[key]

            return True, 0, ""


def client_ip(headers, fallback: str | None) -> str:
    """
    Resolve the real client IP behind a reverse proxy.

    X-Forwarded-For is "client, proxy1, proxy2". The leftmost entries are
    supplied by the caller and can be forged, so we count from the right:
    TRUSTED_PROXY_HOPS = number of proxies we trust that append to the header.
    Set to 0 when running without a proxy (local dev).
    """
    hops = int(os.getenv("TRUSTED_PROXY_HOPS", "1"))
    xff = headers.get("x-forwarded-for")
    if hops > 0 and xff:
        chain = [p.strip() for p in xff.split(",") if p.strip()]
        if chain:
            return chain[-hops] if len(chain) >= hops else chain[0]
    return fallback or "unknown"
