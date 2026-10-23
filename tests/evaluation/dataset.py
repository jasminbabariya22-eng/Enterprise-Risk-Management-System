"""
Golden Natural Language Question Dataset for ERM Copilot.
Comprehensive test cases covering all 18 variation categories across roles and intents.
"""
from typing import List, Dict, Any
from tests.evaluation.taxonomy import ERMRole, ERMIntent, VariationCategory


GOLDEN_QUESTION_DATASET: List[Dict[str, Any]] = [
    # -------------------------------------------------------------
    # 1. GET_MY_RISKS (Risk Owner) - 10 Variations
    # -------------------------------------------------------------
    {
        "test_id": "TC-MYRISK-01",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "Show my open risks.",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities", "RSK-GAS-"],
        }
    },
    {
        "test_id": "TC-MYRISK-02",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.FORMAL.value,
        "question": "Please provide a complete listing of all unresolved risk items assigned to my profile.",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities"],
        }
    },
    {
        "test_id": "TC-MYRISK-03",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.INFORMAL.value,
        "question": "What am I still dealing with right now?",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities"],
        }
    },
    {
        "test_id": "TC-MYRISK-04",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.SHORT.value,
        "question": "my risks",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities", "RSK-GAS-"],
        }
    },
    {
        "test_id": "TC-MYRISK-05",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.LONG.value,
        "question": "Could you check the system and display every single risk item where I am designated as the primary risk owner?",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities", "RSK-GAS-"],
        }
    },
    {
        "test_id": "TC-MYRISK-06",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.TYPOGRAPHICAL.value,
        "question": "Show my opne risks in gas dept",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities"],
        }
    },
    {
        "test_id": "TC-MYRISK-07",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.ABBREVIATION.value,
        "question": "Show my active risks list",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities", "RSK-GAS-"],
        }
    },
    {
        "test_id": "TC-MYRISK-08",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_MY_RISKS.value,
        "variation_category": VariationCategory.CONVERSATIONAL.value,
        "question": "Hey Copilot, I've got a couple of items on my desk. Can you list the risks that belong to me?",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "get_my_risks",
            "key_facts": ["Gas Processing Facilities"],
        }
    },

    # -------------------------------------------------------------
    # 2. GET_PENDING_APPROVALS (Functional Head)
    # -------------------------------------------------------------
    {
        "test_id": "TC-PENDING-01",
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "user_id": 201,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_PENDING_APPROVALS.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "Show pending approvals in my queue.",
        "expected": {
            "authorization": "allow",
            "expected_agent": "agent_approval_workflow",
            "expected_tool": "get_pending_approvals",
            "key_facts": ["RSK-GAS-087"],
        }
    },
    {
        "test_id": "TC-PENDING-02",
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "user_id": 201,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.GET_PENDING_APPROVALS.value,
        "variation_category": VariationCategory.ABBREVIATION.value,
        "question": "What's in my FH approval queue?",
        "expected": {
            "authorization": "allow",
            "expected_agent": "agent_approval_workflow",
            "expected_tool": "get_pending_approvals",
            "key_facts": ["RSK-GAS-087"],
        }
    },

    # -------------------------------------------------------------
    # 3. APPROVE_RISK (Functional Head vs Risk Owner)
    # -------------------------------------------------------------
    {
        "test_id": "TC-APPROVE-FH-01",
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "user_id": 201,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.APPROVE_RISK.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "approve RSK-GAS-087 with remark Approved for RM review",
        "expected": {
            "authorization": "allow",
            "expected_agent": "approval_workflow",
            "expected_tool": "approve_or_reject_risk",
            "key_facts": ["RSK-GAS-087", "approve"],
        }
    },
    {
        "test_id": "TC-APPROVE-RO-DENY-01",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.APPROVE_RISK.value,
        "variation_category": VariationCategory.UNAUTHORIZED.value,
        "question": "I want to approve RSK-GAS-087 now.",
        "expected": {
            "authorization": "deny",
            "expected_agent": "approval_workflow",
            "expected_tool": "approve_or_reject_risk",
            "key_facts": ["not authorized", "denied"],
        }
    },

    # -------------------------------------------------------------
    # 4. REJECT_RISK (Functional Head)
    # -------------------------------------------------------------
    {
        "test_id": "TC-REJECT-FH-01",
        "role": ERMRole.FUNCTIONAL_HEAD.value,
        "user_id": 201,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.REJECT_RISK.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "reject RSK-GAS-087 with remark Inadequate mitigation depth",
        "expected": {
            "authorization": "allow",
            "expected_agent": "approval_workflow",
            "expected_tool": "approve_or_reject_risk",
            "key_facts": ["RSK-GAS-087", "reject"],
        }
    },

    # -------------------------------------------------------------
    # 5. CREATE_RISK (Risk Owner)
    # -------------------------------------------------------------
    {
        "test_id": "TC-CREATRSK-01",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.CREATE_RISK.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "create a new risk for Flare Header Corrosion",
        "expected": {
            "authorization": "allow",
            "expected_agent": "risk_creation_agent",
            "expected_tool": "save_risk",
            "key_facts": ["Flare Header Corrosion"],
        }
    },

    # -------------------------------------------------------------
    # 6. CREATE_TREATMENT (Risk Owner)
    # -------------------------------------------------------------
    {
        "test_id": "TC-TREATMENT-01",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.CREATE_TREATMENT.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "add treatment for RSK-GAS-087",
        "expected": {
            "authorization": "allow",
            "expected_agent": "treatment_management_agent",
            "expected_tool": "save_treatment",
            "key_facts": ["risk"],
        }
    },

    # -------------------------------------------------------------
    # 7. VIEW_HEATMAP (All Roles)
    # -------------------------------------------------------------
    {
        "test_id": "TC-HEATMAP-01",
        "role": ERMRole.RISK_OWNER.value,
        "user_id": 101,
        "dept_id": 2,
        "department": "Gas Processing Facilities",
        "intent": ERMIntent.VIEW_HEATMAP.value,
        "variation_category": VariationCategory.DIRECT.value,
        "question": "show 5x5 heatmap matrix",
        "expected": {
            "authorization": "allow",
            "expected_agent": "orchestrator",
            "expected_tool": "search_risks",
            "key_facts": ["Heatmap"],
        }
    }
]
