"""
Multi-Turn Dialogue and Context-Switching Evaluation Datasets.
Tests multi-turn context preservation, pronoun resolution, and abrupt topic/department switching.
"""
from typing import List, Dict, Any
from tests.evaluation.taxonomy import ERMRole


MULTI_TURN_CONVERSATIONS: List[Dict[str, Any]] = [
    # -------------------------------------------------------------
    # Scenario 1: Multi-Turn Risk Deep-Dive & Action Plan
    # -------------------------------------------------------------
    {
        "dialogue_id": "MT-DEEPDIVE-01",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "description": "Sequential multi-turn risk inspection and treatment drilldown",
        "turns": [
            {
                "turn": 1,
                "input": "Show my open risks.",
                "expected_intent": "GET_MY_RISKS",
                "expected_facts": ["Gas Processing Facilities"]
            },
            {
                "turn": 2,
                "input": "Show audit trail for RSK-GAS-087.",
                "expected_intent": "GET_RISK_DETAILS",
                "expected_facts": ["Inherent Score", "RSK-GAS-087"]
            },
            {
                "turn": 3,
                "input": "Show audit trail for RSK-GAS-087 with action owner.",
                "expected_intent": "GET_RISK_DETAILS",
                "expected_facts": ["Sunil Yadav"]
            },
            {
                "turn": 4,
                "input": "Show audit trail for RSK-GAS-087 with target date.",
                "expected_intent": "GET_RISK_DETAILS",
                "expected_facts": ["2026-11-06"]
            }
        ]
    },

    # -------------------------------------------------------------
    # Scenario 2: Context Switching Across Departments
    # -------------------------------------------------------------
    {
        "dialogue_id": "MT-SWITCH-02",
        "role": ERMRole.RISK_MANAGER.value,
        "user_id": 301,
        "dept_id": 1,
        "description": "Context switching between Gas Processing and Refining Operations",
        "turns": [
            {
                "turn": 1,
                "input": "Show risks for Gas Processing Facilities.",
                "expected_intent": "SEARCH_RISKS",
                "expected_facts": ["RSK-GAS-087"]
            },
            {
                "turn": 2,
                "input": "What about Refining Operations?",
                "expected_intent": "SEARCH_RISKS",
                "expected_facts": ["RSK-REF-001"]
            },
            {
                "turn": 3,
                "input": "Which of those has the highest inherent score?",
                "expected_intent": "SEARCH_RISKS",
                "expected_facts": ["RSK-REF-001", "20"]
            }
        ]
    }
]
