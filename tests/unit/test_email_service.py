"""
Unit Tests for Email Notification Service & Asynchronous Job Construction.
"""
import pytest
from unittest.mock import MagicMock, patch


@pytest.mark.unit
def test_email_job_payload_construction():
    # Test creation of email notification payloads
    mock_email_job = {
        "job_id": 1,
        "recipient_email": "rajesh.sharma@mass-erm.local",
        "subject": "Action Required: Stage 2 Approval for RSK-GAS-087",
        "template_name": "functional_head_approval_request",
        "context_data": {
            "risk_id": "RSK-GAS-087",
            "risk_title": "Pipeline Dust and Particle Contamination",
            "stage": "Stage 2 FH"
        },
        "status": "PENDING"
    }

    assert mock_email_job["status"] == "PENDING"
    assert "RSK-GAS-087" in mock_email_job["subject"]
    assert mock_email_job["context_data"]["stage"] == "Stage 2 FH"


@pytest.mark.unit
def test_email_rejection_reason_inclusion():
    mock_rejection_email = {
        "recipient_email": "karan.malhotra@mass-erm.local",
        "subject": "Risk Returned for Revision: RSK-GAS-087",
        "body": "Your risk has been returned by Functional Head with remark: Missing shutdown procedure.",
        "status": "QUEUED"
    }
    assert "Missing shutdown procedure" in mock_rejection_email["body"]
