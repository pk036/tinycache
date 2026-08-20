"""
Benchmark: TinyCache's O(1) doubly-linked-list LRU vs. a naive O(n)
list-based LRU (the kind of implementation you'd write without thinking
about the underlying data structure).

Run: python benchmark.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from tinycache.cache import TinyCache


class NaiveLRUCache:
    """O(n) LRU cache using a plain list to track recency order."""

    def __init__(self, capacity: int):
        self.capacity = capacity
        self.data = {}
        self.order = []  # order.append on access; O(n) removal + search

    def get(self, key, default=None):
        if key not in self.data:
            return default
        self.order.remove(key)      # O(n)
        self.order.append(key)
        return self.data[key]

    def set(self, key, value):
        if key in self.data:
            self.order.remove(key)  # O(n)
        elif len(self.data) >= self.capacity:
            oldest = self.order.pop(0)  # O(n)
            del self.data[oldest]
        self.data[key] = value
        self.order.append(key)


def time_it(fn, *args, **kwargs):
    start = time.perf_counter()
    fn(*args, **kwargs)
    return time.perf_counter() - start


def run_benchmark(n: int, capacity: int):
    tiny = TinyCache(capacity=capacity, sweep_interval=0)
    naive = NaiveLRUCache(capacity=capacity)

    def workload(cache):
        for i in range(n):
            cache.set(i, i * i)
            cache.get(i // 2)

    tiny_time = time_it(workload, tiny)
    naive_time = time_it(workload, naive)

    speedup = naive_time / tiny_time if tiny_time > 0 else float("inf")

    print(f"n={n:,} operations, capacity={capacity}")
    print(f"  TinyCache (O(1) linked-list LRU): {tiny_time:.4f}s")
    print(f"  Naive LRU (O(n) list-based):      {naive_time:.4f}s")
    print(f"  Speedup: {speedup:.1f}x")
    print()


if __name__ == "__main__":
    print("TinyCache vs. Naive LRU — performance comparison")
    print("(naive list.remove()/list.pop(0) are O(capacity); the gap widens as capacity grows)\n")
    for capacity in (500, 2_000, 8_000):
        run_benchmark(n=capacity * 3, capacity=capacity)
