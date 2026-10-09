"""
RAG Tests: Context Construction and Citation Tracking.
"""
import pytest


def build_augmented_context(chunks):
    citations = []
    context_lines = []
    for idx, c in enumerate(chunks, 1):
        citations.append(c["doc_id"])
        context_lines.append(f"[{idx}] (Source: {c['doc_id']}) {c['text']}")
    return "\n\n".join(context_lines), citations


@pytest.mark.rag
def test_context_construction_preserves_sources():
    chunks = [
        {"doc_id": "SOP-GAS-01", "text": "Purge line before valve change."},
        {"doc_id": "SOP-GAS-02", "text": "Maintain 50 psi minimum pressure."}
    ]
    context_str, citations = build_augmented_context(chunks)
    assert "SOP-GAS-01" in context_str
    assert "SOP-GAS-02" in context_str
    assert citations == ["SOP-GAS-01", "SOP-GAS-02"]
