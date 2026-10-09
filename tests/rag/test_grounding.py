"""
RAG Tests: Grounding Verification, Factuality, and Hallucination Resistance.
"""
import pytest


def verify_answer_groundedness(answer: str, source_facts: list) -> bool:
    """Simple verification checking that key entities in the answer stem from retrieved facts."""
    return any(fact.lower() in answer.lower() for fact in source_facts)


@pytest.mark.rag
def test_answer_grounding_validation():
    source_facts = ["50 psi pressure limit", "ESD valve shutdown sequence"]
    grounded_answer = "According to the procedure, ensure the 50 psi pressure limit is maintained."
    hallucinated_answer = "We recommend replacing the entire nitrogen tank immediately."

    assert verify_answer_groundedness(grounded_answer, source_facts) is True
    assert verify_answer_groundedness(hallucinated_answer, source_facts) is False
