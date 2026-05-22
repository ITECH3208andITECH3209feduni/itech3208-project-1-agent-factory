"""
TTL cache for the Amazon research skill.

PROJ-172 — Sprint 2.

Caches Amazon search results so repeated queries are served instantly
without hitting Amazon and risking rate-limit / bot-detection issues.

The cache is in-memory and lives for the lifetime of the Python process.
Each entry is stored with a timestamp; entries older than the configured
TTL are treated as expired (returned as `None` from `get()` and removable
via `clear_expired()`).
"""

import hashlib
import time
from typing import Optional


def cache_key(query: str) -> str:
    """
    Return an MD5 hash of the lowercased query.

    Lowercasing makes the cache case-insensitive: "Best Laptop" and
    "best laptop" map to the same key, so we don't store duplicate
    entries for queries that mean the same thing.

    Args:
        query: The user's search query.

    Returns:
        A 32-character hex MD5 digest of `query.lower().strip()`.
    """
    normalised = query.lower().strip().encode("utf-8")
    return hashlib.md5(normalised).hexdigest()


class TTLCache:
    """
    A simple in-memory cache with a time-to-live (TTL) per entry.

    Entries are stored as ``{key: (value, timestamp)}``. An entry is
    considered expired once ``time.time() - timestamp > ttl``.

    Args:
        ttl: Number of seconds an entry stays valid for. Defaults to 3600
            (one hour).
    """

    def __init__(self, ttl: int = 3600):
        self.ttl: int = ttl
        self._store: dict[str, tuple[list, float]] = {}

    def get(self, key: str) -> Optional[list]:
        """
        Return the cached value for ``key``, or ``None`` if the entry is
        missing or expired.

        Expired entries are removed lazily on access so the cache doesn't
        grow forever for keys that are read but never re-set.
        """
        entry = self._store.get(key)
        if entry is None:
            return None

        value, timestamp = entry
        if time.time() - timestamp > self.ttl:
            # Entry has expired — drop it and return None.
            del self._store[key]
            return None

        return value

    def set(self, key: str, value: list) -> None:
        """Store ``value`` under ``key`` with the current timestamp."""
        self._store[key] = (value, time.time())

    def clear_expired(self) -> None:
        """
        Remove every entry whose timestamp is older than the TTL.

        Useful for periodic cleanup (e.g. a background task) so the cache
        doesn't accumulate stale entries that no one is reading.
        """
        now = time.time()
        expired_keys = [
            key
            for key, (_, timestamp) in self._store.items()
            if now - timestamp > self.ttl
        ]
        for key in expired_keys:
            del self._store[key]

    def __len__(self) -> int:
        """Return the number of entries currently in the cache (incl. expired)."""
        return len(self._store)

    def __contains__(self, key: str) -> bool:
        """Return True if the key is in the cache (regardless of expiry)."""
        return key in self._store