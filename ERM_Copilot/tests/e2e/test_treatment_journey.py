"""
End-to-End Conversational Journey: Treatment Management & Progress Updates.
Simulates adding treatments and updating progress.
"""
import pytest
from unittest.mock import patch

from ERM_Copilot.agents.treatment.agent import TreatmentManagementAgent
from ERM_Copilot.models.contracts import AgentRequest


def test_e2e_treatment_management_journey(in_memory_db):
    agent = TreatmentManagementAgent()
    user_id = "101"
    agent.clear_session(user_id)

    mock_risk = {
        "id": 87,
        "risk_id": "RSK-GAS-087",
        "risk_title": "Pipeline Dust and Particle Contamination",
        "dept_name": "Gas Processing Facilities"
    }

    with patch("ERM_Copilot.agents.treatment.agent.erm_db.search_risks", return_value=[mock_risk]), \
         patch("ERM_Copilot.agents.treatment.tools.erm_db.add_risk_treatment", side_effect=in_memory_db.add_risk_treatment):

        # 1. Trigger add treatment
        req1 = AgentRequest(message="add treatment for RSK-GAS-087", user_id=user_id, user_role="Risk Owner", session_id=user_id)
        resp1 = agent.process(req1)
        assert "action plan" in resp1.response.lower()

        # 2. Enter action plan
        req2 = AgentRequest(message="Install automatic pressure relief valves", user_id=user_id, user_role="Risk Owner", session_id=user_id)
        resp2 = agent.process(req2)
        assert "target date" in resp2.response.lower() or "owner" in resp2.response.lower() or "progress" in resp2.response.lower()

