"""
Unit Tests for Specialized ERM Subagents.
Covers RiskCreationAgent, ApprovalWorkflowAgent, and TreatmentManagementAgent state logic.
"""
import pytest
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator
from ERM_Copilot.agents.risk_creation.tools import parse_target_date, parse_progress
from ERM_Copilot.agents.treatment.tools import get_treatments_for_risk_tool


def test_risk_matrix_calculator_all_brackets():
    # Low risk (1x1 to 2x2)
    s1, lvl1, b1 = RiskMatrixCalculator.calculate_score(1, 1)
    assert s1 == 1
    assert lvl1 == "LOW"

    # Medium risk (2x3 = 6)
    s2, lvl2, b2 = RiskMatrixCalculator.calculate_score(2, 3)
    assert s2 == 6
    assert lvl2 == "MEDIUM"

    # High risk (3x4 = 12)
    s3, lvl3, b3 = RiskMatrixCalculator.calculate_score(3, 4)
    assert s3 == 12
    assert lvl3 == "HIGH"

    # Critical risk (4x4 = 16, 5x5 = 25)
    s4, lvl4, b4 = RiskMatrixCalculator.calculate_score(4, 4)
    assert s4 == 16
    assert lvl4 == "CRITICAL"


def test_target_date_parser():
    assert parse_target_date("2026-12-31") == "2026-12-31"
    assert parse_target_date("31-12-2026") == "2026-12-31"
    # Relative date "+30 days"
    rel = parse_target_date("+30 days")
    assert rel is not None
    assert len(rel) == 10 # YYYY-MM-DD


def test_progress_parser():
    assert parse_progress("50%") == 50
    assert parse_progress("progress is 75 percent") == 75
    assert parse_progress("invalid text") is None
    assert parse_progress("150%") is None # Exceeds 100
