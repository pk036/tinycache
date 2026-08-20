"""
tinycache.api
--------------
A small FastAPI service exposing TinyCache over HTTP, so it behaves like a
minimal Redis-style cache server. Run with:

    uvicorn tinycache.api:app --reload
"""

from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from .cache import TinyCache

app = FastAPI(
    title="TinyCache",
    description="A tiny in-memory LRU+TTL cache service, built from scratch.",
    version="0.1.0",
)

cache = TinyCache(capacity=1000, default_ttl=None, sweep_interval=5.0)


class SetRequest(BaseModel):
    value: Any
    ttl: Optional[float] = None  # seconds; omit/null = never expires


@app.get("/")
def root():
    return {"service": "tinycache", "status": "ok"}


@app.get("/cache/{key}")
def get_key(key: str):
    _MISSING = object()
    value = cache.get(key, default=_MISSING)
    if value is _MISSING:
        raise HTTPException(status_code=404, detail=f"key '{key}' not found or expired")
    return {"key": key, "value": value}


@app.put("/cache/{key}")
def set_key(key: str, body: SetRequest):
    cache.set(key, body.value, ttl=body.ttl)
    return {"key": key, "value": body.value, "ttl": body.ttl}


@app.delete("/cache/{key}")
def delete_key(key: str):
    deleted = cache.delete(key)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"key '{key}' not found")
    return {"key": key, "deleted": True}


@app.get("/keys")
def list_keys(limit: int = Query(default=100, le=1000)):
    return {"keys": cache.keys()[:limit]}


@app.get("/stats")
def get_stats():
    return cache.stats()


@app.post("/clear")
def clear_cache():
    cache.clear()
    return {"cleared": True}
