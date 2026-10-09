"""
Authentication & Harness Context Fixtures.
"""
from typing import Dict, Any
from ERM_Copilot.ai_harness.context import HarnessContext
from tests.fixtures.users import TEST_USERS


def get_harness_context_for_role(role_key: str) -> HarnessContext:
    user = TEST_USERS[role_key]
    return HarnessContext.build_from_auth(
        user_id=user["user_id"],
        user_role=user["role_name"],
        dept_id=user["dept_id"],
        dept_name=user["dept_name"],
        session_id=f"sess-{role_key}",
        request_id=f"req-{role_key}-01"
    )
