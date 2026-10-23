"""
End-to-End Integration Test for Risk Owner Copilot.
Scenario: A Risk Owner in Gas Processing Facilities creates 'Gas Leakage At Compressor Seal Skid'.
Verifies the complete 14-step state-driven conversational risk creation workflow against the database.
"""
import sys
import unittest
from pathlib import Path

# Ensure root workspace is on path
root_dir = str(Path(__file__).resolve().parents[2])
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

from ERM_Copilot import erm_copilot_agent, AgentRequest
from ERM_Copilot.services.db_service import erm_db


class TestRiskOwnerCopilotE2E(unittest.TestCase):
    """Test full multi-turn conversational risk creation scenario for Gas Processing Facilities."""

    @classmethod
    def setUpClass(cls):
        try:
            conn = erm_db._get_connection()
            conn.close()
        except Exception as e:
            raise unittest.SkipTest(f"Live PostgreSQL database not available: {e}")

    def setUp(self):
        self.user_id = 8
        self.user_role = "Risk Owner"
        self.dept_id = 2
        self.dept_name = "Gas Processing Facilities"
        self.metadata = {
            "role": self.user_role,
            "user_id": str(self.user_id),
            "dept_id": self.dept_id,
            "dept_name": self.dept_name
        }

    def test_complete_risk_owner_creation_workflow(self):
        """
        Executes the full conversational sequence:
        Initiation (Title provided) -> 2. Co-Owner -> 3. Description -> 4. Inherent Assessment
        -> 5. Mitigation -> 6. Current Assessment -> 7. Action Plan -> 8. Action Owner
        -> 9. Target Date -> 10. Status -> 11. Validate -> 12. Preview -> 13. Confirm -> 14. Persist -> Success
        """
        # Step 0: Risk Owner initiates with title in prompt
        req0 = AgentRequest(
            message="Create a new risk for gas leakage at compressor seal skid",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res0 = erm_copilot_agent.process(req0)
        self.assertIn("Step 2/10: Risk Co-Owner", res0.response)
        self.assertIn("Gas Leakage", res0.response)

        # Step 2: Assign Co-Owner
        req1 = AgentRequest(
            message="Assign Co-Owner Rajesh Sharma",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res1 = erm_copilot_agent.process(req1)
        self.assertIn("Step 3/10: Risk Description", res1.response)

        # Step 3: Select Description
        req2 = AgentRequest(
            message="Option 1 Description",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res2 = erm_copilot_agent.process(req2)
        self.assertIn("Step 4/10: Inherent Risk Assessment", res2.response)

        # Step 4: Inherent Assessment (3 x 4 = 12 [HIGH])
        req3 = AgentRequest(
            message="Likelihood 3 Impact 4",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res3 = erm_copilot_agent.process(req3)
        self.assertIn("Step 5/10: Mitigation", res3.response)
        self.assertIn("12 / 25 [HIGH]", res3.response)

        # Step 5: Select Mitigation
        req4 = AgentRequest(
            message="Option 1 Engineering Control",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res4 = erm_copilot_agent.process(req4)
        self.assertIn("Step 6/10: Current / Residual Risk Assessment", res4.response)

        # Step 6: Current Assessment (2 x 2 = 4 [LOW])
        req5 = AgentRequest(
            message="Likelihood 2 Impact 2",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res5 = erm_copilot_agent.process(req5)
        self.assertIn("Step 7/10: Action Plan", res5.response)
        self.assertIn("4 / 25 [LOW]", res5.response)

        # Step 7: Select Action Plan
        req6 = AgentRequest(
            message="Option 1 Action Plan",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res6 = erm_copilot_agent.process(req6)
        self.assertIn("Step 8/10: Assign Action Owner", res6.response)

        # Step 8: Assign Action Owner
        req7 = AgentRequest(
            message="Assign Action Owner Sunil Yadav",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res7 = erm_copilot_agent.process(req7)
        self.assertIn("Step 9/10: Target Completion Date", res7.response)

        # Step 9: Provide Target Date
        req8 = AgentRequest(
            message="31 December 2026",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res8 = erm_copilot_agent.process(req8)
        self.assertIn("Step 10/10: Governance Status", res8.response)

        # Step 10: Select Status -> Automatically Validates & Displays Step 12 Preview
        req9 = AgentRequest(
            message="Submit to Functional Head",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res9 = erm_copilot_agent.process(req9)
        self.assertIn("Risk Creation – Final Review", res9.response)
        self.assertIn("Gas Leakage", res9.response)
        self.assertIn("12 / 25 [HIGH]", res9.response)
        self.assertIn("4 / 25 [LOW]", res9.response)
        self.assertIn("2026-12-31", res9.response)
        self.assertIn("Submitted to Functional Head", res9.response)
        self.assertIn("Do you want to save this risk?", res9.response)

        # Step 13/14: Confirm and Save to Database
        req10 = AgentRequest(
            message="Confirm and Save",
            user_id=str(self.user_id),
            user_role=self.user_role,
            metadata=self.metadata
        )
        res10 = erm_copilot_agent.process(req10)
        self.assertIn("Risk Created Successfully", res10.response)
        self.assertIn("Risk ID", res10.response)
        self.assertIn("RSK-", res10.response)


if __name__ == "__main__":
    unittest.main()
