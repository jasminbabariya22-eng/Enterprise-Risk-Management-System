"""
Tier 5: Cross-Encoder & Reranker Score Cache for ERM Copilot.
Caches reranking scores for (Query, Document_ID) pairs to prevent redundant heavy cross-encoder inferences.
"""
import hashlib
from typing import Dict, Any, Optional, List, Tuple
from collections import OrderedDict
import logging

logger = logging.getLogger("ERM_Copilot.cache.reranker")


class RerankerCache:
    """
    Caches reranking scores between search query and risk document chunk.
    """
    def __init__(self, max_size: int = 5000):
        self.max_size = max_size
        self._cache: OrderedDict[str, float] = OrderedDict()
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _make_key(query: str, doc_id: str, model: str = "bge-reranker-large") -> str:
        norm_q = " ".join(query.strip().lower().split())
        raw = f"{model}::{norm_q}::{doc_id}"
        return hashlib.sha256(raw.encode('utf-8')).hexdigest()

    def get_score(self, query: str, doc_id: str, model: str = "bge-reranker-large") -> Optional[float]:
        key = self._make_key(query, doc_id, model)
        if key not in self._cache:
            self.misses += 1
            return None

        self._cache.move_to_end(key)
        self.hits += 1
        return self._cache[key]

    def set_score(self, query: str, doc_id: str, score: float, model: str = "bge-reranker-large"):
        key = self._make_key(query, doc_id, model)
        if len(self._cache) >= self.max_size and key not in self._cache:
            self._cache.popitem(last=False)
        self._cache[key] = score
        self._cache.move_to_end(key)

    def invalidate_all(self):
        self._cache.clear()

    def get_stats(self) -> Dict[str, Any]:
        total = self.hits + self.misses
        ratio = (self.hits / total * 100) if total > 0 else 0.0
        return {
            "cached_scores": len(self._cache),
            "hits": self.hits,
            "misses": self.misses,
            "hit_ratio_pct": round(ratio, 2)
        }


# Singleton instance
erm_reranker_cache = RerankerCache(max_size=5000)
