"""
Human Confirmation Management for ERM AI Harness.
Guarantees explicit human-in-the-loop signoff for high-impact, state-changing actions
(e.g., risk approval, risk rejection, new risk creation persistence, treatment modification).
"""
from __future__ import annotations

import hashlib
import json
import time
import uuid
from typing import Any, Dict, Optional, Tuple
from ERM_Copilot.ai_harness.exceptions import (
    ConfirmationMismatchError,
    ConfirmationRequiredError,
    ToolValidationError,
)


class ConfirmationManager:
    """
    Coordinates and validates explicit confirmation tokens and fingerprints.
    
    Prevents:
    1. Cross-action hijacking (e.g., token for Risk A used on Risk B).
    2. Cross-user replay (token created for User X confirmed by User Y).
    3. Stale execution (expired confirmation state).
    4. Implicit/assumed confirmation without explicit user intent.
    """

    CONFIRMATION_EXPIRY_SECONDS = 900  # 15 minutes

    @staticmethod
    def compute_action_fingerprint(
        action_name: str,
        user_id: str,
        risk_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Compute deterministic SHA-256 fingerprint representing the exact proposed action.
        """
        canonical_params = {}
        if parameters:
            # Exclude transient/ephemeral keys from fingerprint
            for k, v in sorted(parameters.items()):
                if k not in ("request_id", "run_id", "timestamp", "session_id", "token"):
                    canonical_params[k] = v

        payload = {
            "action": str(action_name).strip().lower(),
            "user_id": str(user_id).strip(),
            "risk_id": str(risk_id).strip().upper() if risk_id else "",
            "params": canonical_params,
        }
        serialized = json.dumps(payload, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    @classmethod
    def create_pending_confirmation(
        cls,
        action_name: str,
        user_id: str,
        user_role: str,
        risk_id: Optional[str] = None,
        parameters: Optional[Dict[str, Any]] = None,
        summary_text: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a secure pending confirmation object with a unique token and fingerprint.
        """
        token = f"conf-{uuid.uuid4().hex[:16]}"
        now = time.time()
        fingerprint = cls.compute_action_fingerprint(
            action_name=action_name,
            user_id=user_id,
            risk_id=risk_id,
            parameters=parameters,
        )

        return {
            "token": token,
            "action_name": action_name,
            "user_id": str(user_id),
            "user_role": str(user_role),
            "risk_id": risk_id,
            "parameters": parameters or {},
            "fingerprint": fingerprint,
            "status": "PENDING",
            "created_at": now,
            "expires_at": now + cls.CONFIRMATION_EXPIRY_SECONDS,
            "summary": summary_text or f"Confirmation required for action '{action_name}'.",
        }

    @classmethod
    def validate_confirmation(
        cls,
        pending_state: Optional[Dict[str, Any]],
        executing_user_id: str,
        executing_action: str,
        executing_params: Optional[Dict[str, Any]] = None,
        executing_risk_id: Optional[str] = None,
    ) -> bool:
        """
        Verify that a pending confirmation matches the current user, action, parameters, and time window.
        Raises ConfirmationMismatchError on any discrepancy.
        """
        if not pending_state:
            raise ConfirmationMismatchError("No pending confirmation state found. Action requires prior preview and signoff.")

        # Check expiration
        now = time.time()
        expires_at = pending_state.get("expires_at", 0)
        if now > expires_at:
            raise ConfirmationMismatchError("The confirmation request has expired (exceeded 15-minute window). Please request a fresh preview.")

        # Check status
        status = pending_state.get("status", "PENDING")
        if status == "CANCELLED":
            raise ConfirmationMismatchError("The pending action was explicitly cancelled by the user.")
        if status == "EXECUTED":
            raise ConfirmationMismatchError("This confirmation token has already been executed and cannot be reused.")

        # Check user identity match
        expected_user = str(pending_state.get("user_id", "")).strip()
        actual_user = str(executing_user_id).strip()
        if expected_user != actual_user:
            raise ConfirmationMismatchError(
                f"Confirmation identity mismatch: Token belongs to user '{expected_user}', but request came from '{actual_user}'."
            )

        # Check action match
        expected_action = str(pending_state.get("action_name", "")).strip().lower()
        actual_action = str(executing_action).strip().lower()
        if expected_action != actual_action:
            raise ConfirmationMismatchError(
                f"Confirmation action mismatch: Token is for '{expected_action}', but attempted execution is '{actual_action}'."
            )

        # Check risk_id match if applicable
        if executing_risk_id or pending_state.get("risk_id"):
            expected_risk = str(pending_state.get("risk_id") or "").strip().upper()
            actual_risk = str(executing_risk_id or "").strip().upper()
            if expected_risk and expected_risk != actual_risk:
                raise ConfirmationMismatchError(
                    f"Confirmation target mismatch: Token is bound to risk '{expected_risk}', cannot execute on '{actual_risk}'."
                )

        # Check fingerprint match
        current_fingerprint = cls.compute_action_fingerprint(
            action_name=executing_action,
            user_id=executing_user_id,
            risk_id=executing_risk_id or pending_state.get("risk_id"),
            parameters=executing_params or pending_state.get("parameters"),
        )
        stored_fingerprint = pending_state.get("fingerprint")
        if stored_fingerprint and current_fingerprint != stored_fingerprint:
            raise ConfirmationMismatchError(
                "Confirmation payload tampered or mismatched: Action arguments have changed since preview generation."
            )

        return True


confirmation_manager = ConfirmationManager()
