"""
Unit Tests for Risk Calculation, 5x5 Matrix Logic, and Risk State Transitions.
"""
import pytest
from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator


@pytest.mark.unit
def test_5x5_risk_matrix_boundary_combinations():
    # 1. Minimum bound (1x1)
    s_min, lvl_min, badge_min = RiskMatrixCalculator.calculate_score(1, 1)
    assert s_min == 1
    assert lvl_min == "LOW"

    # 2. Maximum bound (5x5)
    s_max, lvl_max, badge_max = RiskMatrixCalculator.calculate_score(5, 5)
    assert s_max == 25
    assert lvl_max == "CRITICAL"

    # 3. Medium Threshold (2x3 = 6)
    s_med, lvl_med, badge_med = RiskMatrixCalculator.calculate_score(2, 3)
    assert s_med == 6
    assert lvl_med == "MEDIUM"

    # 4. High Threshold (3x4 = 12)
    s_high, lvl_high, badge_high = RiskMatrixCalculator.calculate_score(3, 4)
    assert s_high == 12
    assert lvl_high == "HIGH"

    # 5. Critical Threshold (4x4 = 16)
    s_crit, lvl_crit, badge_crit = RiskMatrixCalculator.calculate_score(4, 4)
    assert s_crit == 16
    assert lvl_crit == "CRITICAL"


@pytest.mark.unit
def test_risk_matrix_clamping():
    # Negative/zero should clamp to 1
    s_clamp_low, _, _ = RiskMatrixCalculator.calculate_score(0, -5)
    assert s_clamp_low == 1

    # Over 5 should clamp to 5
    s_clamp_high, _, _ = RiskMatrixCalculator.calculate_score(10, 8)
    assert s_clamp_high == 25


@pytest.mark.unit
def test_likelihood_impact_word_parsing():
    parsed_probable_major = RiskMatrixCalculator.parse_likelihood_impact("Likelihood: Probable, Impact: Major")
    assert parsed_probable_major == (4, 4)

    parsed_remote_negligible = RiskMatrixCalculator.parse_likelihood_impact("remote likelihood and negligible impact")
    assert parsed_remote_negligible == (1, 1)
