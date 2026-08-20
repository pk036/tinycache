"""
tinycache.cache
----------------
A thread-safe, in-memory LRU cache with optional per-key TTL (time-to-live)
expiration, implemented from scratch using a doubly linked list + hashmap
for O(1) get/set/evict operations.

Why not just use collections.OrderedDict?
OrderedDict.move_to_end() and popitem() are O(1) amortized in CPython, but
this implementation exists to demonstrate the underlying mechanics explicitly
(node pointers, eviction policy, lazy + active TTL expiration) rather than
relying on a built-in that hides them.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class _Node:
    key: Any
    value: Any
    expires_at: Optional[float]  # epoch seconds; None = never expires
    prev: "_Node" = None
    next: "_Node" = None


class TinyCache:
    """
    Thread-safe LRU cache with optional TTL per entry.

    Parameters
    ----------
    capacity : int
        Maximum number of entries. Least-recently-used entries are evicted
        once capacity is exceeded.
    default_ttl : float | None
        Default seconds-to-live applied to entries that don't specify their
        own TTL in `set()`. None means entries never expire by default.
    sweep_interval : float
        How often (seconds) a background thread actively sweeps and removes
        expired entries, in addition to the lazy check done on access.
        Set to 0 to disable the background sweeper (lazy expiration only).
    """

    def __init__(
        self,
        capacity: int = 128,
        default_ttl: Optional[float] = None,
        sweep_interval: float = 5.0,
    ):
        if capacity <= 0:
            raise ValueError("capacity must be a positive integer")

        self.capacity = capacity
        self.default_ttl = default_ttl

        self._map: dict[Any, _Node] = {}
        self._lock = threading.RLock()

        # Sentinel head/tail nodes simplify list edge cases.
        self._head = _Node(key=None, value=None, expires_at=None)
        self._tail = _Node(key=None, value=None, expires_at=None)
        self._head.next = self._tail
        self._tail.prev = self._head

        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.expirations = 0

        self._stop_sweep = threading.Event()
        self._sweep_thread = None
        if sweep_interval > 0:
            self._sweep_thread = threading.Thread(
                target=self._sweep_loop, args=(sweep_interval,), daemon=True
            )
            self._sweep_thread.start()

    # ---------- internal linked-list helpers ----------

    def _remove_node(self, node: _Node) -> None:
        node.prev.next = node.next
        node.next.prev = node.prev

    def _insert_at_front(self, node: _Node) -> None:
        node.next = self._head.next
        node.prev = self._head
        self._head.next.prev = node
        self._head.next = node

    def _move_to_front(self, node: _Node) -> None:
        self._remove_node(node)
        self._insert_at_front(node)

    def _evict_lru(self) -> None:
        lru_node = self._tail.prev
        if lru_node is self._head:
            return
        self._remove_node(lru_node)
        del self._map[lru_node.key]
        self.evictions += 1

    def _is_expired(self, node: _Node, now: float) -> bool:
        return node.expires_at is not None and node.expires_at <= now

    # ---------- public API ----------

    def set(self, key: Any, value: Any, ttl: Optional[float] = "__default__") -> None:
        """Insert or update a key. `ttl=None` means never expires; omit to
        use the cache's default_ttl."""
        if ttl == "__default__":
            ttl = self.default_ttl
        expires_at = time.time() + ttl if ttl is not None else None

        with self._lock:
            if key in self._map:
                node = self._map[key]
                node.value = value
                node.expires_at = expires_at
                self._move_to_front(node)
                return

            node = _Node(key=key, value=value, expires_at=expires_at)
            self._map[key] = node
            self._insert_at_front(node)

            if len(self._map) > self.capacity:
                self._evict_lru()

    def get(self, key: Any, default: Any = None) -> Any:
        with self._lock:
            node = self._map.get(key)
            if node is None:
                self.misses += 1
                return default

            if self._is_expired(node, time.time()):
                self._remove_node(node)
                del self._map[key]
                self.expirations += 1
                self.misses += 1
                return default

            self._move_to_front(node)
            self.hits += 1
            return node.value

    def delete(self, key: Any) -> bool:
        with self._lock:
            node = self._map.pop(key, None)
            if node is None:
                return False
            self._remove_node(node)
            return True

    def __contains__(self, key: Any) -> bool:
        return self.get(key, default=_MISSING) is not _MISSING

    def __len__(self) -> int:
        with self._lock:
            return len(self._map)

    def clear(self) -> None:
        with self._lock:
            self._map.clear()
            self._head.next = self._tail
            self._tail.prev = self._head

    def stats(self) -> dict:
        with self._lock:
            total = self.hits + self.misses
            hit_rate = self.hits / total if total else 0.0
            return {
                "size": len(self._map),
                "capacity": self.capacity,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(hit_rate, 4),
                "evictions": self.evictions,
                "expirations": self.expirations,
            }

    def keys(self):
        with self._lock:
            return list(self._map.keys())

    # ---------- background TTL sweeper ----------

    def _sweep_loop(self, interval: float) -> None:
        while not self._stop_sweep.wait(interval):
            now = time.time()
            with self._lock:
                expired_keys = [
                    k for k, n in self._map.items() if self._is_expired(n, now)
                ]
                for k in expired_keys:
                    node = self._map.pop(k)
                    self._remove_node(node)
                    self.expirations += 1

    def stop(self) -> None:
        """Stop the background sweep thread (call on shutdown if used)."""
        self._stop_sweep.set()
        if self._sweep_thread is not None:
            self._sweep_thread.join(timeout=1)


class _Missing:
    def __repr__(self):
        return "<MISSING>"


_MISSING = _Missing()
