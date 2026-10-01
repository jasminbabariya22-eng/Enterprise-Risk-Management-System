"""
High-Performance Response Caching Engine for ERM Copilot.
Provides TTL-based, role-aware LRU caching with automatic invalidation and telemetry metrics.
"""
import time
import hashlib
import json
from typing import Dict, Any, Optional, Tuple
from collections import OrderedDict
import logging

logger = logging.getLogger("ERM_Copilot.cache.response")


class CacheEntry:
    def __init__(self, value: Any, ttl_seconds: int, metadata: Optional[Dict[str, Any]] = None):
        self.value = value
        self.created_at = time.time()
        self.expires_at = self.created_at + ttl_seconds
        self.metadata = metadata or {}

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class ResponseCache:
    """
    Role-Scoped, TTL-based LRU Cache for read-only ERM AI responses.
    """
    def __init__(self, max_size: int = 500, default_ttl: int = 600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, CacheEntry] = OrderedDict()
        
        # Telemetry metrics
        self.hits = 0
        self.misses = 0
        self.saved_latency_ms = 0.0

    @staticmethod
    def generate_cache_key(query: str, user_role: Optional[str] = "", dept_id: Optional[Any] = "") -> str:
        """
        Creates a deterministic hash key combining normalized query, role, and department scope.
        Ensures cross-department security and RBAC data isolation.
        """
        normalized = " ".join(query.strip().lower().split())
        raw_key = f"q:{normalized}|r:{str(user_role).lower()}|d:{str(dept_id)}"
        return hashlib.sha256(raw_key.encode('utf-8')).hexdigest()

    def get(self, query: str, user_role: Optional[str] = "", dept_id: Optional[Any] = "") -> Optional[Any]:
        """Retrieves a cached response if valid and not expired."""
        key = self.generate_cache_key(query, user_role, dept_id)
        
        if key not in self._cache:
            self.misses += 1
            return None

        entry = self._cache[key]
        if entry.is_expired():
            del self._cache[key]
            self.misses += 1
            logger.debug(f"Cache expired for key: {key[:8]}")
            return None

        # Move to end for LRU policy
        self._cache.move_to_end(key)
        self.hits += 1
        # Track estimated latency saved (typical LLM inference ~1500ms)
        self.saved_latency_ms += 1200.0
        logger.info(f"⚡ Cache HIT for query: '{query[:40]}...' (Saved ~1.2s)")
        return entry.value

    def set(self, query: str, value: Any, user_role: Optional[str] = "", dept_id: Optional[Any] = "", ttl: Optional[int] = None, metadata: Optional[Dict[str, Any]] = None):
        """Stores a response in cache with TTL and LRU eviction."""
        if not value:
            return

        key = self.generate_cache_key(query, user_role, dept_id)
        effective_ttl = ttl if ttl is not None else self.default_ttl

        # Evict oldest entry if capacity reached
        if len(self._cache) >= self.max_size and key not in self._cache:
            evicted_key, _ = self._cache.popitem(last=False)
            logger.debug(f"Cache capacity reached. Evicted oldest key: {evicted_key[:8]}")

        self._cache[key] = CacheEntry(value, effective_ttl, metadata)
        self._cache.move_to_end(key)
        logger.debug(f"Cached response for key: {key[:8]} (TTL: {effective_ttl}s)")

    def invalidate_all(self):
        """Flushes the entire cache (e.g. after a global schema or risk register update)."""
        cleared_count = len(self._cache)
        self._cache.clear()
        logger.info(f"Cache invalidated. Flushed {cleared_count} entries.")

    def get_stats(self) -> Dict[str, Any]:
        """Returns cache telemetry and performance statistics."""
        total_requests = self.hits + self.misses
        hit_ratio = (self.hits / total_requests * 100) if total_requests > 0 else 0.0
        return {
            "cached_entries": len(self._cache),
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "total_requests": total_requests,
            "hit_ratio_pct": round(hit_ratio, 2),
            "estimated_saved_latency_ms": round(self.saved_latency_ms, 2)
        }


# Global Singleton Instance for ERM Copilot
erm_response_cache = ResponseCache(max_size=1000, default_ttl=900)  # 15 mins default TTL
