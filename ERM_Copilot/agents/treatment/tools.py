"""
Database Operations and Tools for Treatment Management Agent.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from ERM_Copilot.services.db_service import erm_db


def update_treatment_progress_tool(treatment_id: int, progress: int, modified_by: int) -> Dict[str, Any]:
    """Execute direct progress update on an existing action plan."""
    return erm_db.update_treatment_progress(
        treatment_id=treatment_id,
        progress=progress,
        modified_by=modified_by
    )


def reassign_treatment_owner_tool(treatment_id: int, new_action_owner_id: int, modified_by: int) -> Dict[str, Any]:
    """Reassign the responsible Action Owner on an existing action plan."""
    return erm_db.reassign_treatment_owner(
        treatment_id=treatment_id,
        new_action_owner_id=new_action_owner_id,
        modified_by=modified_by
    )


def add_risk_treatment_tool(
    risk_register_id: int,
    action_plan: str,
    action_owner_id: int,
    target_date: Optional[str],
    progress: int,
    action_status_id: int,
    created_by: int
) -> Dict[str, Any]:
    """Insert a new treatment record linked to a risk register."""
    return erm_db.add_risk_treatment(
        risk_register_id=risk_register_id,
        action_plan=action_plan,
        action_owner_id=action_owner_id,
        target_date=target_date,
        progress=progress,
        action_status_id=action_status_id,
        created_by=created_by
    )


def get_treatments_for_risk_tool(risk_identifier: str, dept_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Query all treatment records for a given risk code."""
    return erm_db.get_treatments_for_risk(risk_identifier, dept_id=dept_id)
