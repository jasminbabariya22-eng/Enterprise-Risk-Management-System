"""
Risk item fixtures covering single, multiple, and multi-stage lifecycle states.
"""
from typing import Dict, Any, List

TEST_RISKS: Dict[str, Dict[str, Any]] = {
    "RSK-GAS-087": {
        "risk_register_id": 87,
        "risk_id": "RSK-GAS-087",
        "risk_name": "Pipeline Dust and Particle Contamination",
        "risk_description": "High velocity particulate accumulation in export gas pipeline.",
        "dept_id": 2,
        "dept_name": "Gas Processing Facilities",
        "risk_owner_id": 101,
        "risk_owner_name": "Karan Malhotra",
        "risk_co_owner_id": None,
        "risk_status": 2,  # Stage 2 (Submitted to FH)
        "risk_function_head_approval_status": 0,
        "risk_manager_approval_status": 0,
        "risk_head_approval_status": 0,
        "inherent_likelihood": 4,
        "inherent_impact": 4,
        "inherent_score": 16,
        "current_likelihood": 2,
        "current_impact": 3,
        "current_score": 6,
        "treatments": [
            {
                "treatment_id": 1,
                "action_plan": "Install inline particulate filtration units.",
                "action_owner_id": 101,
                "progress": 30,
                "target_date": "2026-12-31"
            }
        ]
    },
    "RSK-REF-001": {
        "risk_register_id": 1,
        "risk_id": "RSK-REF-001",
        "risk_name": "Crude Distillation Column Top Tray Corrosion",
        "risk_description": "Severe wall thinning observed in atmospheric column upper sections.",
        "dept_id": 3,
        "dept_name": "Refining Operations",
        "risk_owner_id": 102,
        "risk_owner_name": "Suresh Verma",
        "risk_status": 3,  # Stage 3 (Submitted to RM)
        "risk_function_head_approval_status": 1,
        "risk_manager_approval_status": 0,
        "risk_head_approval_status": 0,
        "inherent_likelihood": 5,
        "inherent_impact": 4,
        "inherent_score": 20,
        "current_likelihood": 3,
        "current_impact": 3,
        "current_score": 9,
        "treatments": []
    }
}
