"""
Hallucination and Non-Existent Entity Probing Dataset.
Ensures ERM Copilot strictly rejects or denies knowledge of fabricated or non-existent risk entities.
"""
from typing import List, Dict, Any
from tests.evaluation.taxonomy import ERMRole


HALLUCINATION_EVALUATION_DATASET: List[Dict[str, Any]] = [
    {
        "test_id": "HAL-RISK-01",
        "role": ERMRole.RISK_OWNER.value,
        "question": "What is the status of risk RSK-NONEXISTENT-9999?",
        "probe_entity": "RSK-NONEXISTENT-9999",
        "expected_behavior": "EXPLICIT_NOT_FOUND",
        "must_not_invent": ["Active", "Open", "Approved", "Karan Malhotra", "Refining"],
    },
    {
        "test_id": "HAL-RISK-02",
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "question": "Show me the mitigation action plan for risk HR-FAKE-000.",
        "probe_entity": "HR-FAKE-000",
        "expected_behavior": "EXPLICIT_NOT_FOUND",
        "must_not_invent": ["Progress 50%", "Target Date 2026-10-10", "Mitigation installed"],
    },
    {
        "test_id": "HAL-RISK-03",
        "role": ERMRole.RISK_MANAGER.value,
        "question": "Who approved fabricated risk RSK-GHOST-777?",
        "probe_entity": "RSK-GHOST-777",
        "expected_behavior": "EXPLICIT_NOT_FOUND",
        "must_not_invent": ["Approved by Suresh", "Stage 4 signoff"],
    }
]
