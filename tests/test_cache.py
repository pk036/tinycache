import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from tinycache.cache import TinyCache


def make_cache(**kwargs):
    # sweep_interval=0 disables the background thread so tests are deterministic
    kwargs.setdefault("sweep_interval", 0)
    return TinyCache(**kwargs)


def test_basic_set_get():
    c = make_cache(capacity=3)
    c.set("a", 1)
    assert c.get("a") == 1


def test_missing_key_returns_default():
    c = make_cache(capacity=3)
    assert c.get("nope") is None
    assert c.get("nope", default="fallback") == "fallback"


def test_lru_eviction_order():
    c = make_cache(capacity=2)
    c.set("a", 1)
    c.set("b", 2)
    c.get("a")          # 'a' is now most-recently-used
    c.set("c", 3)        # should evict 'b', the least-recently-used
    assert c.get("b") is None
    assert c.get("a") == 1
    assert c.get("c") == 3
    assert c.stats()["evictions"] == 1


def test_update_existing_key_moves_to_front():
    c = make_cache(capacity=2)
    c.set("a", 1)
    c.set("b", 2)
    c.set("a", 100)      # update, 'a' becomes most-recently-used
    c.set("c", 3)        # should evict 'b', not 'a'
    assert c.get("a") == 100
    assert c.get("b") is None
    assert c.get("c") == 3


def test_ttl_expiration():
    c = make_cache(capacity=10)
    c.set("a", 1, ttl=0.05)
    assert c.get("a") == 1
    time.sleep(0.1)
    assert c.get("a") is None
    assert c.stats()["expirations"] == 1


def test_ttl_none_never_expires():
    c = make_cache(capacity=10, default_ttl=0.05)
    c.set("a", 1, ttl=None)  # explicit override of default_ttl
    time.sleep(0.1)
    assert c.get("a") == 1


def test_default_ttl_applies_when_not_specified():
    c = make_cache(capacity=10, default_ttl=0.05)
    c.set("a", 1)  # no ttl passed -> uses default_ttl
    time.sleep(0.1)
    assert c.get("a") is None


def test_delete():
    c = make_cache(capacity=10)
    c.set("a", 1)
    assert c.delete("a") is True
    assert c.get("a") is None
    assert c.delete("a") is False


def test_contains():
    c = make_cache(capacity=10)
    c.set("a", 1)
    assert "a" in c
    assert "b" not in c


def test_len_and_clear():
    c = make_cache(capacity=10)
    c.set("a", 1)
    c.set("b", 2)
    assert len(c) == 2
    c.clear()
    assert len(c) == 0


def test_stats_hit_rate():
    c = make_cache(capacity=10)
    c.set("a", 1)
    c.get("a")   # hit
    c.get("a")   # hit
    c.get("b")   # miss
    stats = c.stats()
    assert stats["hits"] == 2
    assert stats["misses"] == 1
    assert stats["hit_rate"] == pytest.approx(2 / 3, rel=1e-3)


def test_invalid_capacity_raises():
    with pytest.raises(ValueError):
        TinyCache(capacity=0)
