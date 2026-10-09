"""
Unit Tests for ConfirmationManager and Action Fingerprinting.
Verifies token creation, parameter determinism, expiration, and mismatch detection.
"""
import pytest
import time
from ERM_Copilot.ai_harness.confirmation import confirmation_manager, ConfirmationManager
from ERM_Copilot.ai_harness.exceptions import ConfirmationMismatchError


def test_action_fingerprint_determinism():
    fp1 = ConfirmationManager.compute_action_fingerprint(
        action_name="approve_or_reject_risk",
        user_id="201",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Verified safeguards"}
    )
    fp2 = ConfirmationManager.compute_action_fingerprint(
        action_name="approve_or_reject_risk",
        user_id="201",
        risk_id="RSK-GAS-087",
        parameters={"remark": "Verified safeguards", "action": "approve"} # Reversed param order
    )
    assert fp1 == fp2
    assert len(fp1) == 64 # SHA-256


def test_action_fingerprint_sensitivity_to_changes():
    fp_base = ConfirmationManager.compute_action_fingerprint(
        action_name="approve_or_reject_risk",
        user_id="201",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Verified"}
    )
    fp_different_remark = ConfirmationManager.compute_action_fingerprint(
        action_name="approve_or_reject_risk",
        user_id="201",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Different remark"}
    )
    fp_different_risk = ConfirmationManager.compute_action_fingerprint(
        action_name="approve_or_reject_risk",
        user_id="201",
        risk_id="RSK-REF-001",
        parameters={"action": "approve", "remark": "Verified"}
    )
    assert fp_base != fp_different_remark
    assert fp_base != fp_different_risk


def test_pending_confirmation_creation():
    state = confirmation_manager.create_pending_confirmation(
        action_name="approve_or_reject_risk",
        user_id="201",
        user_role="Functional Head",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Approved"}
    )
    assert state["token"].startswith("conf-")
    assert state["status"] == "PENDING"
    assert state["user_id"] == "201"
    assert state["risk_id"] == "RSK-GAS-087"
    assert state["expires_at"] > state["created_at"]


def test_validate_confirmation_success():
    state = confirmation_manager.create_pending_confirmation(
        action_name="approve_or_reject_risk",
        user_id="201",
        user_role="Functional Head",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Approved"}
    )
    assert confirmation_manager.validate_confirmation(
        pending_state=state,
        executing_user_id="201",
        executing_action="approve_or_reject_risk",
        executing_params={"action": "approve", "remark": "Approved"},
        executing_risk_id="RSK-GAS-087"
    ) is True


def test_validate_confirmation_identity_mismatch():
    state = confirmation_manager.create_pending_confirmation(
        action_name="approve_or_reject_risk",
        user_id="201",
        user_role="Functional Head",
        risk_id="RSK-GAS-087",
        parameters={"action": "approve", "remark": "Approved"}
    )
    with pytest.raises(ConfirmationMismatchError):
        confirmation_manager.validate_confirmation(
            pending_state=state,
            executing_user_id="999", # Impersonator
            executing_action="approve_or_reject_risk",
            executing_params={"action": "approve", "remark": "Approved"},
            executing_risk_id="RSK-GAS-087"
        )
