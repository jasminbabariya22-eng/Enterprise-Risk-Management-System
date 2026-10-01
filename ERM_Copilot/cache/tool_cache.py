"""
Tier 2: Tool & Database Query Cache for ERM Copilot.
Caches repeated PostgreSQL queries (departments, risk registers, audit trails, user resolutions).
"""
import time
import hashlib
import json
from typing import Dict, Any, Optional, List, Callable
from collections import OrderedDict
import logging

logger = logging.getLogger("ERM_Copilot.cache.tool")


class ToolQueryCache:
    """
    LRU + TTL Cache for Database & Tool queries with parameter hashing.
    Prevents redundant database roundtrips for identical SQL/API lookups.
    """
    def __init__(self, max_size: int = 1000, default_ttl: int = 300):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _make_key(func_name: str, args: tuple, kwargs: dict) -> str:
        serialized_args = json.dumps([str(a) for a in args], sort_keys=True)
        serialized_kwargs = json.dumps({k: str(v) for k, v in kwargs.items()}, sort_keys=True)
        raw = f"{func_name}::{serialized_args}::{serialized_kwargs}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get(self, func_name: str, *args, **kwargs) -> Optional[Any]:
        key = self._make_key(func_name, args, kwargs)
        if key not in self._cache:
            self.misses += 1
            return None

        entry = self._cache[key]
        if time.time() > entry["expires_at"]:
            del self._cache[key]
            self.misses += 1
            return None

        self._cache.move_to_end(key)
        self.hits += 1
        logger.debug(f"[Tier 2 Tool Cache] HIT for {func_name}")
        return entry["data"]

    def set(self, func_name: str, data: Any, ttl: Optional[int] = None, *args, **kwargs):
        if data is None:
            return
        key = self._make_key(func_name, args, kwargs)
        effective_ttl = ttl if ttl is not None else self.default_ttl

        if len(self._cache) >= self.max_size and key not in self._cache:
            self._cache.popitem(last=False)

        self._cache[key] = {
            "data": data,
            "expires_at": time.time() + effective_ttl
        }
        self._cache.move_to_end(key)

    def invalidate_all(self):
        cleared = len(self._cache)
        self._cache.clear()
        logger.info(f"[Tier 2 Tool Cache] Flushed {cleared} entries.")

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        ratio = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "cached_entries": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_pct": round(ratio, 2)
        }


# Singleton instance
erm_tool_cache = ToolQueryCache(max_size=1000, default_ttl=300)
