"""
Unified Multi-Tier Cache Manager for ERM Copilot.
Orchestrates all 6 Caching Tiers (Response, Tool, Embedding, Retrieval, Reranker, KV Prefix).
"""
from typing import Dict, Any
import logging

from ERM_Copilot.cache.response_cache import erm_response_cache
from ERM_Copilot.cache.tool_cache import erm_tool_cache
from ERM_Copilot.cache.embedding_cache import erm_embedding_cache
from ERM_Copilot.cache.retrieval_cache import erm_retrieval_cache
from ERM_Copilot.cache.reranker_cache import erm_reranker_cache
from ERM_Copilot.cache.prefix_cache import erm_prefix_cache, PrefixKVCacheOptimizer

logger = logging.getLogger("ERM_Copilot.cache.manager")


class MultiTierCacheManager:
    """Central orchestrator for 6-Tier ERM Caching Architecture."""

    @classmethod
    def invalidate_all_tiers(cls):
        """Flushes dynamic data caches when state changes occur (e.g. new risk, status change)."""
        erm_response_cache.invalidate_all()
        erm_tool_cache.invalidate_all()
        erm_retrieval_cache.invalidate_all()
        logger.info("🛡️ Multi-tier cache invalidation complete across all dynamic tiers.")

    @classmethod
    def get_telemetry_report(cls) -> Dict[str, Any]:
        """Returns consolidated metrics across all 6 caching tiers."""
        resp_stats = erm_response_cache.get_stats()
        tool_stats = erm_tool_cache.get_stats()
        emb_stats = erm_embedding_cache.get_stats()
        ret_stats = erm_retrieval_cache.get_stats()
        rerank_stats = erm_reranker_cache.get_stats()

        total_hits = (
            resp_stats["hits"] + tool_stats["hits"] +
            emb_stats["hits"] + ret_stats["hits"] + rerank_stats["hits"]
        )
        total_misses = (
            resp_stats["misses"] + tool_stats["misses"] +
            emb_stats["misses"] + ret_stats["misses"] + rerank_stats["misses"]
        )
        total_requests = total_hits + total_misses
        overall_hit_ratio = (total_hits / total_requests * 100) if total_requests > 0 else 0.0

        return {
            "tier_1_response_cache": resp_stats,
            "tier_2_tool_db_cache": tool_stats,
            "tier_3_embedding_cache": emb_stats,
            "tier_4_retrieval_cache": ret_stats,
            "tier_5_reranker_cache": rerank_stats,
            "tier_6_kv_prefix_cache": {
                "prefix_hash": PrefixKVCacheOptimizer.get_static_prefix_hash()[:12],
                "status": "active"
            },
            "overall_summary": {
                "total_cache_hits": total_hits,
                "total_cache_misses": total_misses,
                "overall_hit_ratio_pct": round(overall_hit_ratio, 2),
                "estimated_saved_latency_ms": resp_stats.get("estimated_saved_latency_ms", 0.0)
            }
        }


# Global Unified Manager Instance
cache_manager = MultiTierCacheManager()
