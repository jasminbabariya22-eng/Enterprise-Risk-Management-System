"""
Unit Tests for Home Service workload and role-scoped summary KPIs.
"""
import pytest
from unittest.mock import MagicMock

from ERM_API.app.services.home_service import (
    get_score_and_level,
    determine_approval_stage,
    get_home_workload_and_summary
)


def test_get_score_and_level():
    # Low score
    score, level, color = get_score_and_level(2, 2)
    assert score == 4
    assert level == "Low"
    assert color == "#10B981"

    # Medium score
    score, level, color = get_score_and_level(3, 3)
    assert score == 9
    assert level == "Medium"
    assert color == "#F59E0B"

    # High score
    score, level, color = get_score_and_level(3, 5)
    assert score == 15
    assert level == "High"
    assert color == "#F97316"

    # Critical score
    score, level, color = get_score_and_level(5, 4)
    assert score == 20
    assert level == "Critical"
    assert color == "#EF4444"

    # None / Empty
    score, level, color = get_score_and_level(None, None)
    assert score == 0
    assert level == "Not Assessed"


def test_determine_approval_stage():
    # Stage 1: Functional Head Review
    r1 = MagicMock(
        risk_function_head_approval_status=None,
        risk_manager_approval_status=None,
        risk_head_approval_status=None
    )
    stage, badge = determine_approval_stage(r1)
    assert "Stage 1" in stage
    assert badge == "warning"

    # Stage 2: Risk Manager Review
    r2 = MagicMock(
        risk_function_head_approval_status=1,
        risk_manager_approval_status=None,
        risk_head_approval_status=None
    )
    stage, badge = determine_approval_stage(r2)
    assert "Stage 2" in stage
    assert badge == "info"

    # Stage 3: Risk Head Final Review
    r3 = MagicMock(
        risk_function_head_approval_status=1,
        risk_manager_approval_status=1,
        risk_head_approval_status=None
    )
    stage, badge = determine_approval_stage(r3)
    assert "Stage 3" in stage
    assert badge == "primary"

    # Fully Approved
    r4 = MagicMock(
        risk_function_head_approval_status=1,
        risk_manager_approval_status=1,
        risk_head_approval_status=1
    )
    stage, badge = determine_approval_stage(r4)
    assert "Approved" in stage
    assert badge == "success"

    # Rejected / Returned
    r5 = MagicMock(
        risk_function_head_approval_status=-1,
        risk_manager_approval_status=None,
        risk_head_approval_status=None
    )
    stage, badge = determine_approval_stage(r5)
    assert "Needs Revision" in stage
    assert badge == "danger"


def test_home_workload_and_summary_admin_structure():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 42
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    user = {
        "id": 1,
        "role_name": "Admin",
        "user_type_name": "Admin",
        "department_id": 1
    }

    res = get_home_workload_and_summary(db, user)
    assert res["role"] == "Admin"
    assert res["role_category"] == "admin"
    assert "card_1" in res["summary"]
    assert "card_2" in res["summary"]
    assert "card_3" in res["summary"]
    assert "card_4" in res["summary"]
    assert isinstance(res["workload"], list)


def test_home_workload_and_summary_risk_owner_scoping():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 5
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    user = {
        "id": 12,
        "role_name": "Risk Owner",
        "user_type_name": "Risk Owner",
        "department_id": 3
    }

    res = get_home_workload_and_summary(db, user)
    assert res["role"] == "Risk Owner"
    assert res["role_category"] == "risk_owner"
    assert res["user_id"] == 12
    assert "My Owned Risks" in res["summary"]["card_1"]["label"]


def test_workload_stable_keys_and_deduplication():
    db = MagicMock()
    # Mock scalars
    db.query.return_value.filter.return_value.scalar.return_value = 2

    # Mock risk item
    mock_risk = MagicMock()
    mock_risk.risk_register_id = 101
    mock_risk.risk_id = "RSK-101"
    mock_risk.risk_name = "Test Pipeline Leakage"
    mock_risk.dept_id = 2
    mock_risk.department.dept_name = "Gas Processing"
    mock_risk.risk_owner.log_id = "jdoe"
    mock_risk.risk_descriptions = []
    mock_risk.risk_function_head_approval_status = None
    mock_risk.risk_manager_approval_status = None
    mock_risk.risk_head_approval_status = None
    mock_risk.created_on = None

    # Mock treatment item
    mock_treatment = MagicMock()
    mock_treatment.risk_treatment_id = 55
    mock_treatment.risk_description_id = 10
    mock_treatment.risk_register_id = 101
    mock_treatment.risk_id = "RSK-101"
    mock_treatment.action_plan = "Install emergency valve"
    mock_treatment.progress = "In Progress"
    mock_treatment.target_date = None

    # Setup queries: First query returns mock_risk, subsequent returns mock_treatment
    query_mock = MagicMock()
    query_mock.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.side_effect = [
        [mock_risk, mock_risk],  # intentionally duplicate risk to test deduplication
        [],                      # rejected_owned
        [mock_treatment]         # treatments
    ]
    db.query.return_value = query_mock

    user = {
        "id": 7,
        "role_name": "Functional Head",
        "department_id": 2
    }

    res = get_home_workload_and_summary(db, user)
    workload = res["workload"]

    # Verify deduplication: despite duplicate in mock, exactly 1 risk item present
    risk_items = [i for i in workload if i["type"] == "risk"]
    assert len(risk_items) == 1
    assert risk_items[0]["key"] == "rsk_101_warning"
    assert risk_items[0]["category"] == "approval"

    # Verify treatment item is present with stable key
    treatment_items = [i for i in workload if i["type"] == "treatment"]
    assert len(treatment_items) == 1
    assert treatment_items[0]["key"] == "trt_55"
    assert treatment_items[0]["category"] == "treatment"


def test_multi_role_and_function_head_alias():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 0
    db.query.return_value.options.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []

    # Test "Function Head" alias resolves correctly to functional_head
    user = {
        "id": 8,
        "role_name": "Function Head",
        "department_id": 4
    }

    res = get_home_workload_and_summary(db, user)
    assert res["role_category"] == "functional_head"
    assert "Dept Stage 1 Approvals" in res["summary"]["card_1"]["label"]

