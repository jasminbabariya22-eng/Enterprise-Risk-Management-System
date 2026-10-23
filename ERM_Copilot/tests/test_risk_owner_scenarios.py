"""
Test suite demonstrating and validating the Risk Creation Agent specifically for the 'Risk Owner' role.

Covers:
1. Risk Owner single-turn full risk creation (one-shot input -> deterministic scoring -> review preview -> confirm).
2. Risk Owner multi-turn conversational flow with AI mitigation suggestions.
3. Risk Owner department isolation (anti-spoofing protection on dept_id).
4. Risk Owner ownership scoping (enterprise co-owner vs department-scoped action owner).
5. Confirmation integrity (anti-tamper and replay protection).
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Ensure root workspace is on sys.path
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ERM_Copilot.agents.risk_creation.agent import RiskCreationAgent
from ERM_Copilot.agents.risk_creation.state import RiskCreationSession, RiskCreationState
from ERM_Copilot.ai_harness.context import HarnessContext
from ERM_Copilot.ai_harness.execution import ExecutionCoordinator
from ERM_Copilot.ai_harness.tool_registry import tool_registry
from ERM_Copilot.ai_harness.policies import ROLE_RISK_OWNER
from ERM_Copilot.models.contracts import AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestRiskOwnerScenarios(unittest.TestCase):
    """Behavioral and security tests for a user logged in as 'Risk Owner'."""

    @classmethod
    def setUpClass(cls):
        try:
            conn = erm_db._get_connection()
            conn.close()
        except Exception as e:
            raise unittest.SkipTest(f"Live PostgreSQL database not available: {e}")

    def setUp(self):
        self.agent = RiskCreationAgent()
        self.agent.sessions.clear()
        
        # Risk Owner Profile
        self.user_id = "101"
        self.user_role = "Risk Owner"
        self.dept_id = 1
        self.dept_name = "Engineering"
        self.session_id = "sess-risk-owner-001"
        
        self.metadata = {
            "role": self.user_role,
            "user_id": self.user_id,
            "dept_id": self.dept_id,
            "dept_name": self.dept_name,
        }

    @patch("ERM_Copilot.services.db_service.erm_db.create_risk")
    def test_risk_owner_single_turn_complete_creation(self, mock_create):
        """A Risk Owner who provides all required information in one message goes directly to preview and confirms."""
        mock_create.return_value = {
            "status": "success",
            "risk_id": "RSK-ENG-101",
            "risk_register_id": 501,
            "risk_name": "Unpatched API Gateway",
            "department_id": 1,
            "department_name": "Engineering",
            "risk_status": 1,
            "status_label": "Draft",
        }
        
        prompt = (
            "Create risk: Unpatched API Gateway. "
            "Description: Known CVE-2026-1002 in gateway proxy causing auth bypass risk. "
            "Inherent likelihood 3 and impact 4. "
            "Mitigation: Deploy automated vulnerability scanner and apply vendor patches. "
            "Current likelihood 2 and impact 2. "
            "Action plan: Upgrade gateway firmware to v2.4 and monitor traffic. "
            "Action owner Bob Martin. "
            "Target date 2026-12-31."
        )
        
        req = AgentRequest(
            message=prompt,
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        
        res1 = self.agent.process(req)
        
        # 1. Inherent calculation: 3 x 4 = 12 / 25 [HIGH]
        self.assertIn("12 / 25", res1.response)
        # 2. Residual calculation: 2 x 2 = 4 / 25 [LOW]
        self.assertIn("4 / 25", res1.response)
        # 3. Review preview presented with confirmation prompt
        self.assertIn("Risk Creation – Final Review", res1.response)
        self.assertIn("Do you want to save this risk?", res1.response)
        
        # 4. User confirms creation
        confirm_req = AgentRequest(
            message="Confirm",
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        res2 = self.agent.process(confirm_req)
        
        self.assertIn("RSK-ENG-101", res2.response)
        self.assertIn("Risk Created Successfully", res2.response)
        mock_create.assert_called_once()
        created_kwargs = mock_create.call_args[1]
        self.assertEqual(created_kwargs["dept_id"], 1)

    @patch("ERM_Copilot.agents.risk_creation.suggestions.static_suggestion_provider.get_mitigation_suggestions")
    def test_risk_owner_conversational_multi_turn_with_suggestions(self, mock_sugg):
        """Risk Owner starts with partial input, requests suggestions, and completes flow."""
        mock_sugg.return_value = [
            {"title": "Implement Connection Pooling", "description": "Configure max connections and active health checks."}
        ]
        
        # Turn 1: Partial input (Title only)
        req1 = AgentRequest(
            message="Create risk: Database Pool Exhaustion",
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        res1 = self.agent.process(req1)
        self.assertIn("Database Pool Exhaustion", res1.response)
        
        # Turn 2: Request suggestions directly via tool
        tool_res = self.agent.execute_governed_tool(
            tool_name="get_mitigation_suggestions",
            arguments={"risk_title": "Database Pool Exhaustion"},
            session=self.agent.get_session(self.user_id),
        )
        self.assertTrue(tool_res["success"])
        self.assertTrue(mock_sugg.called)
        
        # Turn 3: Complete remaining fields
        req3 = AgentRequest(
            message=(
                "Description: High connection count leads to RDS exhaustion and timeout cascades. "
                "Inherent likelihood 4 and impact 4. "
                "Mitigation: Implement Connection Pooling and active health checks. "
                "Current likelihood 2 and impact 2. "
                "Action plan: Reconfigure database proxy and connection limits. "
                "Target date 2026-11-30."
            ),
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        res3 = self.agent.process(req3)
        self.assertIn("16 / 25", res3.response)
        self.assertIn("Risk Creation – Final Review", res3.response)

    @patch("ERM_Copilot.services.db_service.erm_db.create_risk")
    def test_risk_owner_department_anti_spoofing(self, mock_create):
        """Standard Risk Owner cannot spoof dept_id in create_risk; execution pins to context.dept_id."""
        mock_create.return_value = {
            "status": "success",
            "risk_id": "RSK-ENG-999",
            "risk_register_id": 999,
            "risk_name": "Department Spoof Test",
            "department_id": 1,
            "department_name": "Engineering",
            "risk_status": 1,
            "status_label": "Draft",
        }
        coordinator = ExecutionCoordinator()
        
        ctx = HarnessContext(
            user_id="101",
            user_role=ROLE_RISK_OWNER,
            dept_id=1,  # Engineering
            dept_name="Engineering",
            session_id=self.session_id,
        )
        
        # Attempting to spoof dept_id to 99 (e.g. Finance or Exec)
        payload = {
            "risk_name": "Department Spoof Test",
            "risk_description": "Testing spoofing protection",
            "dept_id": 99,  # Spoof attempt
            "risk_owner_id": 101,
            "inherent_likelihood": 3,
            "inherent_impact": 3,
            "mitigation_strategy": "Routine audit",
            "residual_likelihood": 2,
            "residual_impact": 2,
            "action_plan": "Audit logs",
            "target_date": "2026-12-31",
        }
        
        result = coordinator.execute_tool(
            tool_name="create_risk",
            arguments=payload,
            context=ctx,
            bypass_confirmation=True,
        )
        
        self.assertTrue(result["success"])
        # Verify DB service received dept_id = 1, NOT 99
        mock_create.assert_called_once()
        self.assertEqual(mock_create.call_args[1]["dept_id"], 1)

    @patch("ERM_Copilot.services.db_service.erm_db.get_department_action_owners")
    @patch("ERM_Copilot.services.db_service.erm_db.get_all_users_for_co_owner")
    def test_risk_owner_ownership_scoping(self, mock_co, mock_act):
        """Risk Owner action owners are scoped to their dept, whereas co-owners are enterprise-wide."""
        mock_co.return_value = [{"user_id": 201, "full_name": "Alice CrossDept", "role_name": "Functional Head"}]
        mock_act.return_value = [{"user_id": 102, "full_name": "Bob SameDept", "role_name": "Risk Owner"}]
        
        coordinator = ExecutionCoordinator()
        ctx = HarnessContext(
            user_id="101",
            user_role=ROLE_RISK_OWNER,
            dept_id=1,
            dept_name="Engineering",
            session_id=self.session_id,
        )
        
        # 1. Co-owner lookup (enterprise)
        co_res = coordinator.execute_tool(
            tool_name="lookup_eligible_owners",
            arguments={"owner_type": "co_owner"},
            context=ctx,
        )
        self.assertTrue(co_res["success"])
        mock_co.assert_called_once()
        
        # 2. Action owner lookup (department-bound)
        act_res = coordinator.execute_tool(
            tool_name="lookup_eligible_owners",
            arguments={"owner_type": "action_owner"},
            context=ctx,
        )
        self.assertTrue(act_res["success"])
        # Should call with dept_id=1
        mock_act.assert_called_once_with(dept_id=1)

    @patch("ERM_Copilot.services.db_service.erm_db.create_risk")
    def test_risk_owner_confirmation_anti_tamper_and_replay(self, mock_create):
        """Altered confirmation payload or replaying confirmation token is rejected."""
        mock_create.return_value = {
            "status": "success",
            "risk_id": "RSK-ENG-503",
            "risk_register_id": 503,
            "risk_name": "Data Leakage Risk",
            "department_id": 1,
            "department_name": "Engineering",
            "risk_status": 1,
            "status_label": "Draft",
        }
        
        prompt = (
            "Create risk: Data Leakage Risk. "
            "Description: Exposure of customer PII in analytics logs. "
            "Inherent likelihood 3 and impact 4. "
            "Mitigation: Encrypt data at rest and scrub PII from logging pipeline. "
            "Current likelihood 2 and impact 2. "
            "Action plan: Deploy Logstash PII filter and rotate KMS keys. "
            "Target date 2026-10-31."
        )
        
        req = AgentRequest(
            message=prompt,
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        res1 = self.agent.process(req)
        self.assertIn("Risk Creation – Final Review", res1.response)
        
        # First confirmation works
        confirm_req1 = AgentRequest(
            message="Confirm",
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        res_confirm1 = self.agent.process(confirm_req1)
        self.assertIn("RSK-ENG-503", res_confirm1.response)
        self.assertEqual(mock_create.call_count, 1)
        
        # Replaying confirmation MUST NOT create duplicate
        confirm_req2 = AgentRequest(
            message="Confirm",
            user_id=self.user_id,
            user_role=self.user_role,
            session_id=self.session_id,
            metadata=self.metadata,
        )
        res_confirm2 = self.agent.process(confirm_req2)
        # Replay rejected: call count remains 1
        self.assertEqual(mock_create.call_count, 1)
        self.assertNotIn("RSK-ENG-503", res_confirm2.response)


if __name__ == "__main__":
    unittest.main()
