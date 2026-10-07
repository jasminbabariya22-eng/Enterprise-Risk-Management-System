"""
Test suite for Role-Wise Question Suggestion Service.
Verifies:
1. Exact 3 suggestions per supported role.
2. Shared suggestion set between Functional Head, Risk Manager, and Risk Head.
3. Action Owner and Admin suggestions.
4. Safe behavior for unknown/unsupported roles.
5. Role naming normalization variations.
6. Integration with ERMCopilotAgent.
"""
import pytest
from ERM_Copilot.agents.suggestion_service import (
    get_role_suggestions,
    normalize_role,
    APPROVER_SUGGESTIONS,
    APPROVER_ROLES,
    ROLE_SUGGESTIONS,
    StaticSuggestionProvider
)
from ERM_Copilot.agents.agent import ERMCopilotAgent
from ERM_Copilot.models.contracts import AgentRequest


class TestSuggestionServiceUnit:
    """Unit tests for suggestion_service.py."""

    def test_risk_owner_suggestions(self):
        """Risk Owner receives exactly 3 specific suggestions."""
        expected = [
            "Create a new risk",
            "Show my open risks",
            "Show risks that need my action"
        ]
        assert get_role_suggestions("Risk Owner") == expected
        assert get_role_suggestions("risk owner") == expected
        assert get_role_suggestions("risk_owner") == expected
        assert get_role_suggestions("RO") == expected
        assert len(get_role_suggestions("Risk Owner")) == 3

    def test_functional_head_suggestions(self):
        """Functional Head receives exactly 3 approver suggestions."""
        expected = [
            "Show risks pending my approval",
            "Show high and critical risks",
            "Show risks that need my action"
        ]
        assert get_role_suggestions("Functional Head") == expected
        assert get_role_suggestions("functional head") == expected
        assert get_role_suggestions("functional_head") == expected
        assert get_role_suggestions("FH") == expected
        assert len(get_role_suggestions("Functional Head")) == 3

    def test_risk_manager_suggestions(self):
        """Risk Manager receives exactly the same 3 suggestions as Functional Head."""
        expected = [
            "Show risks pending my approval",
            "Show high and critical risks",
            "Show risks that need my action"
        ]
        assert get_role_suggestions("Risk Manager") == expected
        assert get_role_suggestions("risk manager") == expected
        assert get_role_suggestions("risk_manager") == expected
        assert get_role_suggestions("RM") == expected
        assert len(get_role_suggestions("Risk Manager")) == 3

    def test_risk_head_suggestions(self):
        """Risk Head receives exactly the same 3 suggestions as Functional Head."""
        expected = [
            "Show risks pending my approval",
            "Show high and critical risks",
            "Show risks that need my action"
        ]
        assert get_role_suggestions("Risk Head") == expected
        assert get_role_suggestions("risk head") == expected
        assert get_role_suggestions("risk_head") == expected
        assert get_role_suggestions("RH") == expected
        assert get_role_suggestions("CRO") == expected
        assert len(get_role_suggestions("Risk Head")) == 3

    def test_approver_roles_share_same_suggestion_set(self):
        """Verify FH == RM == RH suggestions strictly."""
        fh_sug = get_role_suggestions("Functional Head")
        rm_sug = get_role_suggestions("Risk Manager")
        rh_sug = get_role_suggestions("Risk Head")
        assert fh_sug == rm_sug == rh_sug == APPROVER_SUGGESTIONS

    def test_action_owner_suggestions(self):
        """Action Owner receives exactly 3 specific suggestions."""
        expected = [
            "Show my pending actions",
            "Show my overdue actions",
            "Show my assigned risks"
        ]
        assert get_role_suggestions("Action Owner") == expected
        assert get_role_suggestions("action owner") == expected
        assert get_role_suggestions("action_owner") == expected
        assert get_role_suggestions("AO") == expected
        assert len(get_role_suggestions("Action Owner")) == 3

    def test_admin_suggestions(self):
        """Admin receives exactly 3 specific suggestions."""
        expected = [
            "Show overall risk status",
            "Show high and critical risks",
            "Show risks by department"
        ]
        assert get_role_suggestions("Admin") == expected
        assert get_role_suggestions("admin") == expected
        assert get_role_suggestions("Super Admin") == expected
        assert get_role_suggestions("super_admin") == expected
        assert len(get_role_suggestions("Admin")) == 3

    def test_unknown_or_unsupported_role(self):
        """Unknown role returns empty list [] and does NOT expose Admin or Approver suggestions."""
        res_guest = get_role_suggestions("Guest")
        assert res_guest == []

        res_none = get_role_suggestions(None)
        assert res_none == []

        res_empty = get_role_suggestions("")
        assert res_empty == []

        res_random = get_role_suggestions("Invalid_Role_XYZ")
        assert res_random == []

    def test_custom_provider_extensibility(self):
        """Verify StaticSuggestionProvider implements SuggestionProvider cleanly."""
        provider = StaticSuggestionProvider()
        assert len(provider.get_suggestions("Risk Owner")) == 3


class TestSuggestionServiceAgentIntegration:
    """Integration tests with ERMCopilotAgent."""

    def setup_method(self):
        from ERM_Copilot.agents.approval import approval_agent
        from ERM_Copilot.agents.risk_creation import risk_creation_agent
        from ERM_Copilot.agents.treatment import treatment_management_agent
        approval_agent._sessions.clear()
        risk_creation_agent.sessions.clear()
        treatment_management_agent.sessions.clear()
        self.agent = ERMCopilotAgent()

    def test_risk_owner_greeting_includes_suggestions(self):
        """Test Risk Owner greeting renders the 3 suggestion buttons."""
        req = AgentRequest(
            message="hi",
            user_id="5",
            user_role="Risk Owner",
            metadata={"role": "Risk Owner", "user_id": "5"}
        )
        resp = self.agent.process(req)
        assert resp.metadata.get("intent") == "ROLE_WELCOME_MENU"
        assert "[btn:Create a new risk|Create a new risk]" in resp.response
        assert "[btn:Show my open risks|Show my open risks]" in resp.response
        assert "[btn:Show risks that need my action|Show risks that need my action]" in resp.response

    def test_functional_head_greeting_includes_approver_suggestions(self):
        """Test FH greeting renders the 3 shared approver buttons."""
        req = AgentRequest(
            message="hello",
            user_id="4",
            user_role="Functional Head",
            metadata={"role": "Functional Head", "user_id": "4"}
        )
        resp = self.agent.process(req)
        assert resp.metadata.get("intent") == "ROLE_WELCOME_MENU"
        assert "[btn:Show risks pending my approval|Show risks pending my approval]" in resp.response
        assert "[btn:Show high and critical risks|Show high and critical risks]" in resp.response
        assert "[btn:Show risks that need my action|Show risks that need my action]" in resp.response

    def test_action_owner_greeting_includes_suggestions(self):
        """Test Action Owner greeting renders the 3 action buttons."""
        req = AgentRequest(
            message="hi",
            user_id="8",
            user_role="Action Owner",
            metadata={"role": "Action Owner", "user_id": "8"}
        )
        resp = self.agent.process(req)
        assert resp.metadata.get("intent") == "ROLE_WELCOME_MENU"
        assert "[btn:Show my pending actions|Show my pending actions]" in resp.response
        assert "[btn:Show my overdue actions|Show my overdue actions]" in resp.response
        assert "[btn:Show my assigned risks|Show my assigned risks]" in resp.response
