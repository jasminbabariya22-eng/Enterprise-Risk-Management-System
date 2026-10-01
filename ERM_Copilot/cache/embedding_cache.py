"""
Tier 3: Vector Embedding Cache for ERM Copilot.
Stores precomputed text embedding vectors to avoid duplicate API calls to embedding models.
"""
import hashlib
from typing import List, Dict, Any, Optional
from collections import OrderedDict
import logging

logger = logging.getLogger("ERM_Copilot.cache.embedding")


class EmbeddingCache:
    """
    Stores dense embedding vectors for user queries, risk descriptions, and standard procedures.
    """
    def __init__(self, max_size: int = 5000):
        self.max_size = max_size
        self._cache: OrderedDict[str, List[float]] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _hash_text(text: str, model: str = "text-embedding-3-small") -> str:
        normalized = " ".join(text.strip().lower().split())
        raw = f"{model}::{normalized}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get(self, text: str, model: str = "text-embedding-3-small") -> Optional[List[float]]:
        key = self._hash_text(text, model)
        if key not in self._cache:
            self.misses += 1
            return None

        self._cache.move_to_end(key)
        self.hits += 1
        logger.debug(f"[Tier 3 Embedding Cache] HIT for '{text[:30]}...'")
        return self._cache[key]

    def set(self, text: str, vector: List[float], model: str = "text-embedding-3-small"):
        if not vector:
            return
        key = self._hash_text(text, model)
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._cache.popitem(last=False)
        self._cache[key] = vector
        self._cache.move_to_end(key)

    def invalidate_all(self):
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        ratio = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "cached_vectors": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_pct": round(ratio, 2)
        }


# Singleton instance
erm_embedding_cache = EmbeddingCache(max_size=5000)
