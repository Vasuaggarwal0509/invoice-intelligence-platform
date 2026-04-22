"""Per-IP-per-route rate limiting (in-memory token bucket).

Single-process-only backing. Good enough for Slice 1's single uvicorn
worker; when we scale horizontally, swap the :class:`_Bucket` store for
Redis behind the same :class:`RateLimiter` interface.

Intent is anti-abuse, not fine-grained traffic shaping:
  * Login + OTP: 5/min — blunt credential stuffing and OTP brute force.
  * Upload: 10/min per workspace — blunt mass-upload floods.

Returns :class:`~business_layer.errors.RateLimitedError` with a
``retry_after_seconds`` hint when exhausted; the global handler emits
``429`` + ``Retry-After`` header.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from business_layer.errors import RateLimitedError


@dataclass
class _Bucket:
    """One bucket's state.

    ``tokens`` are decremented on every :meth:`take`; refilled linearly
    up to ``capacity`` at ``refill_per_sec`` rate. ``last_refill`` is a
    monotonic timestamp so clock adjustments can't break accounting.
    """

    capacity: float
    refill_per_sec: float
    tokens: float = field(default=0.0)
    last_refill: float = field(default_factory=time.monotonic)


class RateLimiter:
    """Token-bucket limiter keyed by arbitrary strings.

    Keys are opaque to the limiter — a typical key is
    ``f"{route_group}:{ip}"`` or ``f"{route_group}:{workspace_id}"``.
    Two different routes should use two different ``route_group``
    prefixes so their buckets don't share state.
    """

    def __init__(self) -> None:
        self._buckets: dict[str, _Bucket] = {}
        self._lock = threading.Lock()

    def check(
        self,
        key: str,
        *,
        capacity: int,
        per_seconds: int,
    ) -> None:
        """Consume one token from the bucket for ``key``.

        Args:
            key: Bucket identity (e.g. ``"login:1.2.3.4"``).
            capacity: Max tokens the bucket holds.
            per_seconds: Window the capacity replenishes over — e.g.
                ``capacity=5, per_seconds=60`` → 5 req/min.

        Raises:
            RateLimitedError: When the bucket is empty. Carries
                ``retry_after_seconds`` calculated from the refill rate.
        """
        refill_rate = capacity / float(per_seconds)

        with self._lock:
            now = time.monotonic()
            bucket = self._buckets.get(key)
            if bucket is None:
                # New bucket starts FULL — first N requests are free.
                bucket = _Bucket(
                    capacity=float(capacity),
                    refill_per_sec=refill_rate,
                    tokens=float(capacity),
                    last_refill=now,
                )
                self._buckets[key] = bucket
            else:
                # Linear refill bounded by capacity.
                elapsed = now - bucket.last_refill
                bucket.tokens = min(
                    bucket.capacity,
                    bucket.tokens + elapsed * bucket.refill_per_sec,
                )
                bucket.last_refill = now

            if bucket.tokens < 1.0:
                # Seconds until at least one whole token is available.
                deficit = 1.0 - bucket.tokens
                retry_after = int(max(1.0, deficit / bucket.refill_per_sec))
                raise RateLimitedError(
                    "rate limit exceeded",
                    retry_after_seconds=retry_after,
                    context={"key": key, "capacity": capacity, "per_seconds": per_seconds},
                )

            bucket.tokens -= 1.0

    def reset(self, key: str | None = None) -> None:
        """Clear buckets — used by tests.

        ``key=None`` clears everything; a specific key clears that
        bucket only.
        """
        with self._lock:
            if key is None:
                self._buckets.clear()
            else:
                self._buckets.pop(key, None)


# Module-level singleton. Tests import and call ``.reset()`` in their
# fixtures; production code imports and calls ``.check(...)``.
limiter = RateLimiter()
