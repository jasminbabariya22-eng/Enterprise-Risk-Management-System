"""
RAG Tests: Relevance Ranking and Confidence Score Thresholds.
"""
import pytest


def rank_retrieved_chunks(chunks, threshold: float = 0.75):
    return [c for c in chunks if c.get("similarity", 0.0) >= threshold]


@pytest.mark.rag
def test_ranking_filters_irrelevant_chunks():
    raw_chunks = [
        {"chunk_id": "c1", "similarity": 0.92, "content": "Pipeline maintenance procedure."},
        {"chunk_id": "c2", "similarity": 0.65, "content": "Unrelated canteen menu policy."},
        {"chunk_id": "c3", "similarity": 0.81, "content": "Gas leakage isolation steps."}
    ]
    ranked = rank_retrieved_chunks(raw_chunks, threshold=0.75)
    assert len(ranked) == 2
    assert "c2" not in [c["chunk_id"] for c in ranked]
