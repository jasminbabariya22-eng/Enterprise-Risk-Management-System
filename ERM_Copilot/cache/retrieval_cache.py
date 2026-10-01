"""
Tier 4: Retrieval Document & Candidate Chunk Cache for ERM Copilot.
Caches retrieved top-K risk records, SOPs, and mitigation documents for specific semantic concepts.
"""
import time
import hashlib
import json
from typing import List, Dict, Any, Optional
from collections import OrderedDict
import logging

logger = logging.getLogger("ERM_Copilot.cache.retrieval")


class RetrievalCache:
    """
    Caches retrieved document chunks and candidate risk records for semantic search queries.
    """
    def __init__(self, max_size: int = 2000, default_ttl: int = 600):
        self.max_size = max_size
        self.default_ttl = default_ttl
        self._cache: OrderedDict[str, Dict[str, Any]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _make_key(query: str, top_k: int = 5, filter_dept: Optional[str] = None) -> str:
        norm_q = " ".join(query.strip().lower().split())
        raw = f"{norm_q}::k={top_k}::dept={filter_dept}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get(self, query: str, top_k: int = 5, filter_dept: Optional[str] = None) -> Optional[List[Dict[str, Any]]]:
        key = self._make_key(query, top_k, filter_dept)
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
        logger.debug(f"[Tier 4 Retrieval Cache] HIT for '{query[:30]}...'")
        return entry["chunks"]

    def set(self, query: str, chunks: List[Dict[str, Any]], top_k: int = 5, filter_dept: Optional[str] = None, ttl: Optional[int] = None):
        if not chunks:
            return
        key = self._make_key(query, top_k, filter_dept)
        effective_ttl = ttl if ttl is not None else self.default_ttl

        if len(self._cache) >= self.max_size and key not in self._cache:
            self._cache.popitem(last=False)

        self._cache[key] = {
            "chunks": chunks,
            "expires_at": time.time() + effective_ttl
        }
        self._cache.move_to_end(key)

    def invalidate_all(self):
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        ratio = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "cached_retrievals": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_pct": round(ratio, 2)
        }


# Singleton instance
erm_retrieval_cache = RetrievalCache(max_size=2000, default_ttl=600)
