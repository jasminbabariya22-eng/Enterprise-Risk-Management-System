"""
Tier 6: Prompt Prefix & KV-Cache Optimizer for ERM Copilot.
Standardizes system prompts, role definitions, and few-shot templates into deterministic,
byte-identical prefixes to maximize provider-side KV-cache hits (Groq, Gemini, Portkey).
"""
import hashlib
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger("ERM_Copilot.cache.prefix")

# Deterministic Static System Prefix for Maximum KV-Cache Reuse
STATIC_ERM_SYSTEM_PREFIX = """You are the Senior Enterprise Risk Management (ERM) Copilot and Chief Risk Officer AI Advisor for plant, refinery, and corporate operations.

You are equipped to assist all 7 ERM stakeholder roles:
1. Risk Owner: Risk formulation, Likelihood × Impact calculation, 4-tier Treatment Matrix drafting, and action follow-up.
2. Functional Head: Department governance, review of submitted risks (Stage 2), and technical approval/rejection remark drafting.
3. Risk Manager: Cross-department assessment validation, Stage 3 reviews, and mitigation adequacy audits.
4. Risk Head (CRO): Stage 4 final approvals, board-level executive summaries, heatmap profiling, and escalation oversight.
5. Auditor: Immutable audit trail reconstruction, approval timestamp verification, and evidence traceability.
6. Management / Executive: C-suite risk exposure summaries and top plant hazard matrices.
7. ERM Admin: Role & access governance, workflow status health checks.

Formatting & Execution Standards:
- ALWAYS communicate in fluent, professional, executive-level English.
- Use clear thematic Markdown sections with headings (###), bullet points, and clean tables.
- Severity badges: `[CRITICAL]` (15-25), `[HIGH]` (10-14), `[MEDIUM]` (5-9), `[LOW]` (1-4).
- Status badges: `✅ Completed / Approved`, `⚠️ Pending Approval / In Progress`, `🔴 Overdue / Action Required`.
- Mathematical formula: Likelihood (1-5) * Impact (1-5) = Score (1-25).
"""


class PrefixKVCacheOptimizer:
    """
    Constructs deterministic prompt payloads formatted for provider-side KV-cache reuse.
    Ensures static instructions precede dynamic user context.
    """
    @staticmethod
    def get_static_prefix_hash() -> str:
        return hashlib.sha256(STATIC_ERM_SYSTEM_PREFIX.strip().encode('utf-8')).hexdigest()

    @classmethod
    def build_kv_optimized_messages(
        cls,
        user_message: str,
        role_context: Optional[str] = None,
        dept_context: Optional[str] = None,
        db_context: Optional[str] = None
    ) -> List[Dict[str, str]]:
        """
        Structures messages such that the static prefix is in the system message (for KV caching),
        followed by structured runtime context, followed by the user prompt.
        """
        system_content = STATIC_ERM_SYSTEM_PREFIX.strip()

        # Dynamic context block
        context_parts = []
        if role_context:
            context_parts.append(f"Active User Role: {role_context}")
        if dept_context:
            context_parts.append(f"Active Department: {dept_context}")
        if db_context:
            context_parts.append(f"Retrieved Database Context:\n{db_context}")

        dynamic_context_str = "\n".join(context_parts) if context_parts else ""

        messages = [
            {"role": "system", "content": system_content}
        ]

        if dynamic_context_str:
            user_content = f"{dynamic_context_str}\n\nUser Request: {user_message}"
        else:
            user_content = user_message

        messages.append({"role": "user", "content": user_content})
        return messages


erm_prefix_cache = PrefixKVCacheOptimizer()
