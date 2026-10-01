"""
FastAPI ESM Core API Client for ERM Copilot.
"""
import os
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta, timezone
import requests
try:
    from jose import jwt
except ImportError:
    try:
        import jwt
    except ImportError:
        jwt = None

from ERM_Copilot.config.settings import settings

logger = logging.getLogger("ERM_Copilot.services.api_client")

ESM_API_BASE_URL = settings.ESM_API_BASE_URL
JWT_SECRET_KEY = os.getenv("ESM_JWT_SECRET_KEY", "0eeedb8821a0a275fc8afb816145a44cee60bfc7f55f51b1f091cca47596cdb0")
JWT_ALGORITHM = "HS256"


class ERMFastAPIClient:
    """Production client bridging ERM AI Copilot to existing FastAPI backend."""

    def __init__(self, base_url: str = ESM_API_BASE_URL):
        self.base_url = base_url.rstrip("/")

    def create_auth_token(
        self,
        user_id: int = 5,
        log_id: str = "refining_ro",
        user_type_name: str = "Risk Owner",
        dept_id: int = 1,
        role_id: int = 5,
        role_name: str = "Risk Owner"
    ) -> str:
        """Generate official JWT Token conforming to FastAPI get_current_user dependency."""
        payload = {
            "id": int(user_id),
            "logid": str(log_id),
            "role_id": int(role_id),
            "role_name": str(role_name),
            "dept_id": int(dept_id),
            "user_type_name": str(user_type_name),
            "exp": datetime.now(timezone.utc) + timedelta(hours=24)
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    def _resolve_user_info(self, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not user_context:
            user_context = {}
        raw_user_id = user_context.get("user_id") or user_context.get("id") or "5"
        raw_dept_id = user_context.get("dept_id") or 1
        raw_role = user_context.get("role") or "Risk Owner"
        raw_log_id = user_context.get("log_id") or str(raw_user_id)

        return {
            "user_id": int(raw_user_id) if str(raw_user_id).isdigit() else 5,
            "log_id": str(raw_log_id),
            "dept_id": int(raw_dept_id) if str(raw_dept_id).isdigit() else 1,
            "role_id": 1,
            "user_type_name": str(raw_role)
        }

    def _get_headers(self, user_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        user_info = self._resolve_user_info(user_context)
        token = self.create_auth_token(
            user_id=user_info["user_id"],
            log_id=user_info["log_id"],
            user_type_name=user_info["user_type_name"],
            dept_id=user_info["dept_id"],
            role_id=user_info["role_id"],
            role_name=user_info["user_type_name"]
        )
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}"
        }

    def save_risk(
        self,
        risk_name: str,
        risk_description: str,
        dept_id: Optional[int] = None,
        risk_owner_id: Optional[int] = None,
        risk_co_owner_id: Optional[int] = None,
        inherent_likelihood: int = 4,
        inherent_impact: int = 4,
        current_likelihood: int = 2,
        current_impact: int = 2,
        mitigation: str = "",
        status: int = 1,
        financial_year: str = "2026-2027",
        treatments: Optional[List[Dict[str, Any]]] = None,
        user_context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """Call FastAPI POST /risk/save to create or update risk."""
        url = f"{self.base_url}/risk/save"
        user_info = self._resolve_user_info(user_context)
        headers = self._get_headers(user_context)

        final_dept_id = int(dept_id) if dept_id is not None and str(dept_id).isdigit() else user_info["dept_id"]
        final_owner_id = int(risk_owner_id) if risk_owner_id is not None and str(risk_owner_id).isdigit() else user_info["user_id"]

        processed_treatments = []
        if treatments:
            for t in treatments:
                action_text = t.get("action_plan") if isinstance(t, dict) else str(t)
                target_owner_id = final_owner_id
                processed_treatments.append({
                    "risk_description_id": "0",
                    "risk_register_id": "0",
                    "risk_id": "",
                    "action_plan": action_text,
                    "action_owner_id": target_owner_id,
                    "target_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                    "progress": "0%",
                    "action_status_id": 1,
                    "next_followup_date": (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
                })

        payload = {
            "risk_register": {
                "risk_register_id": "0",
                "risk_name": risk_name,
                "dept_id": final_dept_id,
                "risk_owner_id": final_owner_id,
                "risk_co_owner_id": risk_co_owner_id,
                "financial_year": financial_year,
                "risk_status": int(status),
                "risk_progress": "0%",
                "is_active": "1"
            },
            "risk_description": {
                "risk_description_id": "0",
                "risk_description": risk_description,
                "inherent_risk_likelihood_id": int(inherent_likelihood),
                "inherent_risk_impact_id": int(inherent_impact),
                "mitigation": mitigation,
                "current_risk_likelihood_id": int(current_likelihood),
                "current_risk_impact_id": int(current_impact)
            },
            "risk_treatments": processed_treatments
        }

        try:
            res = requests.post(url, json=payload, headers=headers, timeout=10)
            if res.status_code in [200, 201]:
                data = res.json()
                reg_data = (data.get("data") or [{}])[0] if isinstance(data.get("data"), list) else data.get("data", {})
                return {
                    "status": "success",
                    "source": "fastapi_api",
                    "risk_id": reg_data.get("risk_id", f"RSK-REF-{reg_data.get('risk_register_id', '001')}"),
                    "risk_register_id": reg_data.get("risk_register_id"),
                    "risk_name": risk_name,
                    "department_id": dept_id,
                    "department_name": reg_data.get("department_name") or "Refining",
                    "risk_status": status,
                    "status_label": "Draft" if status == 1 else "Submitted to Functional Head",
                    "inherent_likelihood": inherent_likelihood,
                    "inherent_impact": inherent_impact,
                    "inherent_score": inherent_likelihood * inherent_impact,
                    "created_on": datetime.now(timezone.utc).isoformat(),
                    "treatments": [t["action_plan"] for t in processed_treatments]
                }
            return {"status": "error", "message": res.text}
        except Exception as e:
            logger.error(f"Failed to connect to FastAPI /risk/save: {e}")
            return {"status": "error", "message": str(e)}


# Global singleton instance
erm_api_client = ERMFastAPIClient()
