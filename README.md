# TinyCache

A small in-memory LRU cache with optional per-key TTL expiration, built from
scratch in Python (no `functools.lru_cache`, no `OrderedDict`) and exposed as
a REST service with FastAPI.

I built this to implement the data structure behind most
production caching layers: a **doubly linked list + hashmap** for O(1)
get/set/evict, plus lazy and active TTL expiration.

## Why build this

Every language has a built-in cache/dict with move-to-end semantics. The
point here was to implement the actual mechanics: node pointers, eviction
order, and expiration, and then measure whether that effort pays off against
the naive approach most people reach for first.

## Features

- **O(1) get/set/evict** via doubly linked list + hashmap (not `OrderedDict`)
- **Per-key TTL** — set an expiration in seconds per entry, or a cache-wide default
- **Thread-safe** — `RLock`-protected, safe for concurrent access
- **Background sweeper** — a daemon thread actively evicts expired keys, in
  addition to lazy expiration on access
- **Hit/miss/eviction/expiration stats** for observability
- **REST API** via FastAPI — use it like a tiny Redis over HTTP
- **12 unit tests** covering eviction order, TTL edge cases, and stats

## Architecture

```
┌─────────────┐     GET/PUT/DELETE      ┌──────────────┐
│   FastAPI    │ ──────────────────────▶ │  TinyCache   │
│   (api.py)   │                         │  (cache.py)  │
└─────────────┘                         └──────┬───────┘
                                                │
                                    ┌───────────┴────────────┐
                                    │  hashmap: key → Node    │
                                    │  doubly linked list:    │
                                    │  head ⇄ node ⇄ ... ⇄ tail│
                                    └─────────────────────────┘
```

- **Get**: hashmap lookup → check TTL → move node to front of list → O(1)
- **Set**: hashmap insert/update → insert at front → evict tail if over
  capacity → O(1)
- **Evict**: always removes `tail.prev` (least-recently-used) → O(1)

## Usage

### As a library

```python
from tinycache import TinyCache

cache = TinyCache(capacity=1000, default_ttl=60)  # 60s default TTL

cache.set("user:42", {"name": "Pranavi"})
cache.set("session:abc", "token123", ttl=5)  # overrides default TTL

cache.get("user:42")     # {"name": "Pranavi"}
cache.stats()            # {'size': 2, 'hits': 1, 'misses': 0, ...}
```

### As a REST service

```bash
pip install -r requirements.txt
uvicorn tinycache.api:app --reload --app-dir src
```

```bash
curl -X PUT localhost:8000/cache/foo -H "Content-Type: application/json" \
  -d '{"value": "bar", "ttl": 30}'

curl localhost:8000/cache/foo
# {"key": "foo", "value": "bar"}

curl localhost:8000/stats
# {"size": 1, "capacity": 1000, "hits": 1, "misses": 0, "hit_rate": 1.0, ...}
```

Interactive API docs are auto-generated at `/docs` once the server is running.

## Benchmark: does the O(1) design actually matter?

`benchmark.py` compares TinyCache against a naive LRU cache that uses a plain
Python list for recency tracking (`list.remove()` / `list.pop(0)`, both
O(n)). Results on this machine:

| Capacity | Operations | TinyCache (O(1)) | Naive (O(n)) | Speedup |
|---:|---:|---:|---:|---:|
| 500   | 1,500  | 0.0029s | 0.0013s | 0.4x (naive wins — list ops beat lock overhead at small size) |
| 2,000 | 6,000  | 0.0115s | 0.0177s | 1.5x |
| 8,000 | 24,000 | 0.0429s | 0.2401s | **5.6x** |

The honest finding: at small capacities, the naive version is actually
*faster*, because Python's C-optimized list operations outperform the
threading-lock overhead of the linked-list version on short lists. The O(1)
design only pays off once capacity is large enough that `list.remove()`'s
O(n) cost dominates — which is exactly what the theory predicts, and worth
showing rather than hiding.

Reproduce with `python benchmark.py`.

## Running tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

12/12 tests passing — covers LRU eviction order, TTL expiration (including
default-vs-override TTL), thread-safety-relevant stats, and edge cases like
zero capacity.

## Project structure

```
tinycache/
├── src/tinycache/
│   ├── cache.py      # core LRU+TTL data structure
│   ├── api.py         # FastAPI REST wrapper
│   └── __init__.py
├── tests/
│   └── test_cache.py  # 12 unit tests
├── benchmark.py        # performance comparison vs. naive implementation
├── requirements.txt
└── README.md
```

## What I'd add next

- LFU (least-frequently-used) as an alternative eviction policy
- Persistence (snapshot to disk on shutdown)
- A simple client library so `api.py` isn't the only way to talk to a remote
  instance
