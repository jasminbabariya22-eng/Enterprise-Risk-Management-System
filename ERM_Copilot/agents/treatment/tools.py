"""
Enterprise Risk Management (ERM) - Governed Tools for Treatment Management Agent.
Small, strongly typed tools wrapping database queries and mutations.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from ERM_Copilot.agents.treatment.state import TreatmentSession
from ERM_Copilot.services.db_service import erm_db

logger = logging.getLogger("ERM_Copilot.agents.treatment.tools")


def fetch_risk_info(session: TreatmentSession, risk_identifier: str) -> Optional[Dict[str, Any]]:
    """Retrieve full risk register record by risk code or identifier."""
    if not risk_identifier:
        return None
    try:
        # 1. Direct code lookup
        risk = erm_db.get_risk_by_code(str(risk_identifier).strip())
        if risk:
            return risk

        # 2. Search fallback
        results = erm_db.search_risks(
            keyword=str(risk_identifier).strip(),
            department=session.dept_name,
            limit=5,
        )
        if results:
            target_upper = str(risk_identifier).strip().upper()
            for r in results:
                if str(r.get("risk_id", "")).upper() == target_upper:
                    return r
            return results[0]
        return None
    except Exception as e:
        logger.error(f"Error fetching risk '{risk_identifier}': {e}")
        return None


def fetch_treatment_details(session: TreatmentSession, treatment_id: int) -> Optional[Dict[str, Any]]:
    """Fetch single treatment details by primary key."""
    if not treatment_id:
        return None
    try:
        return erm_db.get_treatment_by_id(int(treatment_id))
    except Exception as e:
        logger.error(f"Error fetching treatment #{treatment_id}: {e}")
        return None


def fetch_treatments_for_risk(session: TreatmentSession, risk_identifier: str) -> List[Dict[str, Any]]:
    """Query active treatment records for a given risk code."""
    if not risk_identifier:
        return []
    try:
        return erm_db.get_treatments_for_risk(str(risk_identifier).strip(), dept_id=session.dept_id)
    except Exception as e:
        logger.error(f"Error fetching treatments for risk '{risk_identifier}': {e}")
        return []


def fetch_eligible_action_owners(session: TreatmentSession, search_term: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return registered eligible action owners for the session department."""
    try:
        owners = erm_db.get_department_action_owners(dept_id=session.dept_id, dept_name=session.dept_name)
        if search_term and str(search_term).strip():
            term = str(search_term).strip().lower()
            owners = [
                u for u in owners
                if term in str(u.get("full_name") or "").lower()
                or term in str(u.get("log_id") or "").lower()
                or term in str(u.get("role_name") or "").lower()
            ]
        return owners
    except Exception as e:
        logger.error(f"Error fetching eligible action owners: {e}")
        return []


def add_risk_treatment_tool(
    risk_register_id: int,
    action_plan: str,
    action_owner_id: int,
    target_date: Optional[str],
    progress: int,
    action_status_id: int,
    created_by: int
) -> Dict[str, Any]:
    """Execute authoritative insert of a new treatment record."""
    return erm_db.add_risk_treatment(
        risk_register_id=int(risk_register_id),
        action_plan=action_plan,
        action_owner_id=int(action_owner_id),
        target_date=target_date,
        progress=int(progress),
        action_status_id=int(action_status_id),
        created_by=int(created_by)
    )


def update_treatment_progress_tool(
    treatment_id: int,
    progress: int,
    modified_by: int,
    remarks: Optional[str] = None
) -> Dict[str, Any]:
    """Execute authoritative progress update on an existing action plan."""
    return erm_db.update_treatment_progress(
        treatment_id=int(treatment_id),
        progress=int(progress),
        modified_by=int(modified_by),
        remarks=remarks
    )


def reassign_treatment_owner_tool(
    treatment_id: int,
    new_action_owner_id: int,
    modified_by: int
) -> Dict[str, Any]:
    """Execute authoritative ownership reassignment on an existing action plan."""
    return erm_db.reassign_treatment_owner(
        treatment_id=int(treatment_id),
        new_action_owner_id=int(new_action_owner_id),
        modified_by=int(modified_by)
    )


def get_treatments_for_risk_tool(risk_identifier: str, dept_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Query all treatment records for a given risk code (legacy compatibility)."""
    return erm_db.get_treatments_for_risk(risk_identifier, dept_id=dept_id)
