"""
PostgreSQL Database Service for MassERS (Schema: ers).
Handles direct parameterized queries, multi-stage governance approvals, 5x5 heatmap distribution, and audit trails.
"""
import os
import re
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import List, Dict, Any, Optional, Set, Tuple
import psycopg2
from psycopg2.extras import RealDictCursor

from ERM_Copilot.config.settings import settings
from ERM_Copilot.cache.tool_cache import erm_tool_cache
from ERM_Copilot.cache.manager import cache_manager

logger = logging.getLogger("ERM_Copilot.services.db_service")

DB_HOST = settings.POSTGRES_HOST
DB_PORT = settings.POSTGRES_PORT
DB_NAME = settings.POSTGRES_DB
DB_USER = settings.POSTGRES_USER
DB_PASS = settings.POSTGRES_PASSWORD
DB_SCHEMA = settings.DB_SCHEMA


class ERMDatabaseService:
    """Service to query and search MassERS risk tables safely across all 7 ERM roles."""

    def __init__(self):
        self.host = DB_HOST
        self.port = DB_PORT
        self.dbname = DB_NAME
        self.user = DB_USER
        self.password = DB_PASS

    def _get_connection(self, readonly: bool = True):
        for p in [self.port, 5432]:
            try:
                conn = psycopg2.connect(
                    host=self.host,
                    port=p,
                    dbname=self.dbname,
                    user=self.user,
                    password=self.password,
                    connect_timeout=3
                )
                if readonly:
                    conn.set_session(readonly=True)
                else:
                    conn.autocommit = True
                return conn
            except Exception:
                continue
        raise ConnectionError(f"Could not connect to PostgreSQL database '{self.dbname}' on port {self.port} or 5432.")

    def search_risks(
        self,
        keyword: Optional[str] = None,
        department: Optional[str] = None,
        status: Optional[int] = None,
        severity_level: Optional[str] = None,
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Search risk register entries with optional filters and severity bands."""
        # Tier 2 Cache Check
        cached = erm_tool_cache.get("search_risks", keyword=keyword, department=department, status=status, severity=severity_level, limit=limit)
        if cached is not None:
            return cached

        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = f"""
                SELECT 
                    r.risk_register_id as id,
                    r.risk_id,
                    r.risk_name as risk_title,
                    r.dept_id as department_id,
                    COALESCE(d.dept_name, 'Enterprise') as department_name,
                    r.risk_status,
                    r.financial_year,
                    COALESCE(rd.risk_description, '') as description,
                    COALESCE(rd.mitigation, '') as mitigation,
                    COALESCE(rd.inherent_risk_likelihood_id, 3) as inherent_likelihood,
                    COALESCE(rd.inherent_risk_impact_id, 3) as inherent_impact,
                    (COALESCE(rd.inherent_risk_likelihood_id, 3) * COALESCE(rd.inherent_risk_impact_id, 3)) as inherent_score,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Risk Owner') as owner_name,
                    r.created_on
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.risk_description rd ON r.risk_register_id = rd.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_users u ON r.risk_owner_id = u.id
                WHERE r.is_deleted = 0
            """
            params = []
            
            if keyword:
                query += " AND (r.risk_name ILIKE %s OR r.risk_id ILIKE %s OR rd.risk_description ILIKE %s)"
                kw_wildcard = f"%{keyword}%"
                params.extend([kw_wildcard, kw_wildcard, kw_wildcard])
                
            if department:
                query += " AND d.dept_name ILIKE %s"
                params.append(f"%{department}%")

            if status:
                query += " AND r.risk_status = %s"
                params.append(status)

            if severity_level:
                sev_lower = severity_level.lower()
                if "crit" in sev_lower:
                    query += " AND (COALESCE(rd.inherent_risk_likelihood_id, 3) * COALESCE(rd.inherent_risk_impact_id, 3)) >= 15"
                elif "high" in sev_lower:
                    query += " AND (COALESCE(rd.inherent_risk_likelihood_id, 3) * COALESCE(rd.inherent_risk_impact_id, 3)) >= 10"
                elif "med" in sev_lower:
                    query += " AND (COALESCE(rd.inherent_risk_likelihood_id, 3) * COALESCE(rd.inherent_risk_impact_id, 3)) BETWEEN 5 AND 9"
                elif "low" in sev_lower:
                    query += " AND (COALESCE(rd.inherent_risk_likelihood_id, 3) * COALESCE(rd.inherent_risk_impact_id, 3)) <= 4"
                
            query += " ORDER BY (COALESCE(rd.inherent_risk_likelihood_id, 3) * COALESCE(rd.inherent_risk_impact_id, 3)) DESC, r.risk_register_id DESC LIMIT %s;"
            params.append(limit)
            
            cur.execute(query, params)
            results = cur.fetchall()
            cur.close()
            conn.close()
            formatted = [dict(r) for r in results]
            # Store in Tier 2 DB cache
            erm_tool_cache.set("search_risks", formatted, ttl=300, keyword=keyword, department=department, status=status, severity=severity_level, limit=limit)
            return formatted
        except Exception as e:
            logger.error(f"Error searching risks: {e}")
            return []

    def get_approval_queues(self, approver_role: str = "all", dept_id: Optional[int] = None, limit: int = 50) -> List[Dict[str, Any]]:
        """Alias for get_pending_approvals to support tool registry and role queries."""
        return self.get_pending_approvals(stage=approver_role, dept_id=dept_id, limit=limit)

    def get_risk_by_code(self, risk_id: str) -> Optional[Dict[str, Any]]:
        """Retrieve authoritative full details for a risk record by identifier or register ID."""
        return self.get_risk_audit_trail(risk_id)

    def get_pending_approvals(self, stage: str = "all", dept_id: Optional[int] = None, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Fetch risks pending approvals at specific governance tiers.
        """
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            status_filter = ""
            params = []

            stage_lower = stage.lower()
            if "function" in stage_lower or "fh" in stage_lower or "2" in stage_lower:
                status_filter = "r.risk_status = 2"
            elif "manager" in stage_lower or "rm" in stage_lower or "3" in stage_lower:
                status_filter = "r.risk_status = 3"
            elif "head" in stage_lower or "rh" in stage_lower or "4" in stage_lower:
                status_filter = "r.risk_status = 4"
            else:
                status_filter = "r.risk_status IN (2, 3, 4)"

            query = f"""
                SELECT 
                    r.risk_register_id as id,
                    r.risk_id,
                    r.risk_name as risk_title,
                    COALESCE(d.dept_name, 'Enterprise') as department_name,
                    r.risk_status,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Risk Owner') as owner_name,
                    COALESCE(rd.risk_description, '') as description,
                    COALESCE(rd.mitigation, '') as mitigation,
                    r.created_on,
                    r.risk_function_head_approval_remark,
                    r.risk_function_head_approval_on,
                    r.risk_manager_approval_remark,
                    r.risk_manager_approved_on
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.risk_description rd ON r.risk_register_id = rd.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_users u ON r.risk_owner_id = u.id
                WHERE r.is_deleted = 0 AND {status_filter}
            """
            if dept_id:
                query += " AND r.dept_id = %s"
                params.append(dept_id)

            query += " ORDER BY r.risk_register_id DESC LIMIT %s;"
            params.append(limit)

            cur.execute(query, params)
            results = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Error fetching pending approvals: {e}")
            return []

    def get_risk_audit_trail(self, risk_id: str) -> Optional[Dict[str, Any]]:
        """Reconstruct complete audit trail and approval lifecycle for a given risk."""
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)

            query = f"""
                SELECT 
                    r.risk_register_id,
                    r.risk_id,
                    r.risk_name,
                    r.dept_id,
                    COALESCE(d.dept_name, 'Enterprise') as department,
                    r.financial_year,
                    r.risk_status,
                    r.created_on,
                    COALESCE(u_owner.first_name || ' ' || u_owner.last_name, u_owner.log_id, 'Risk Owner') as owner_name,
                    COALESCE(u_cr.first_name || ' ' || u_cr.last_name, u_cr.log_id, 'System') as created_by_name,
                    r.modified_on,
                    COALESCE(u_mod.first_name || ' ' || u_mod.last_name, u_mod.log_id, 'System') as modified_by_name,
                    r.risk_function_head_approval_status as fh_status,
                    r.risk_function_head_approval_on as fh_on,
                    r.risk_function_head_approval_remark as fh_remark,
                    COALESCE(u_fh.first_name || ' ' || u_fh.last_name, u_fh.log_id, 'N/A') as fh_approver,
                    r.risk_manager_approval_status as rm_status,
                    r.risk_manager_approved_on as rm_on,
                    r.risk_manager_approval_remark as rm_remark,
                    COALESCE(u_rm.first_name || ' ' || u_rm.last_name, u_rm.log_id, 'N/A') as rm_approver,
                    r.risk_head_approval_status as rh_status,
                    r.risk_head_approved_on as rh_on,
                    r.risk_head_approval_remark as rh_remark,
                    COALESCE(u_rh.first_name || ' ' || u_rh.last_name, u_rh.log_id, 'N/A') as rh_approver,
                    COALESCE(rd.risk_description, '') as description,
                    COALESCE(rd.mitigation, '') as mitigation,
                    COALESCE(rd.inherent_risk_likelihood_id, 1) as inherent_likelihood,
                    COALESCE(rd.inherent_risk_impact_id, 1) as inherent_impact,
                    COALESCE(rd.current_risk_likelihood_id, 1) as current_likelihood,
                    COALESCE(rd.current_risk_impact_id, 1) as current_impact
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.risk_description rd ON r.risk_register_id = rd.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_users u_owner ON r.risk_owner_id = u_owner.id
                LEFT JOIN {DB_SCHEMA}.mst_users u_cr ON r.created_by = u_cr.id
                LEFT JOIN {DB_SCHEMA}.mst_users u_mod ON r.modified_by = u_mod.id
                LEFT JOIN {DB_SCHEMA}.mst_users u_fh ON r.risk_function_head_approval_by = u_fh.id
                LEFT JOIN {DB_SCHEMA}.mst_users u_rm ON r.risk_manager_approval_by = u_rm.id
                LEFT JOIN {DB_SCHEMA}.mst_users u_rh ON r.risk_head_approval_by = u_rh.id
                WHERE r.is_deleted = 0 AND (r.risk_id ILIKE %s OR r.risk_name ILIKE %s)
                LIMIT 1;
            """
            import re
            id_match = re.search(r'\b(RSK-[A-Z]+-\d+|[A-Z]{2,5}-\d{3,5}|RSK-\d+)\b', risk_id, re.IGNORECASE)
            clean_target = id_match.group(1).upper() if id_match else risk_id.strip()
            wildcard = f"%{clean_target}%"
            cur.execute(query, [wildcard, wildcard])
            row = cur.fetchone()
            if not row:
                cur.close()
                conn.close()
                return None

            data = dict(row)

            cur.execute(f"""
                SELECT 
                    t.risk_treatment_id,
                    t.action_plan,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Action Owner') as action_owner,
                    t.target_date,
                    COALESCE(s.status_name, 'In Progress') as status,
                    COALESCE(t.progress, '0%%') as progress
                FROM {DB_SCHEMA}.risk_treatment t
                LEFT JOIN {DB_SCHEMA}.mst_users u ON t.action_owner_id = u.id
                LEFT JOIN {DB_SCHEMA}.mst_status s ON t.action_status_id = s.id
                WHERE t.risk_register_id = %s AND (t.is_deleted = 0 OR t.is_deleted IS NULL)
                ORDER BY t.risk_treatment_id ASC;
            """, [data["risk_register_id"]])
            treatments = [dict(t) for t in cur.fetchall()]
            data["treatments"] = treatments

            cur.close()
            conn.close()
            return data
        except Exception as e:
            logger.error(f"Error fetching risk audit trail: {e}")
            return None

    def get_overdue_actions(self, dept_id: Optional[int] = None, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetch action plans and follow-ups from ers.risk_treatment."""
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = f"""
                SELECT 
                    t.risk_treatment_id as id,
                    r.risk_id,
                    r.risk_name as risk_title,
                    COALESCE(d.dept_name, 'Enterprise') as department_name,
                    COALESCE(t.action_plan, 'Preventative Maintenance & Inspection') as action_plan,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Action Owner') as action_owner,
                    t.target_date,
                    COALESCE(s.status_name, 'In Progress') as status,
                    COALESCE(t.progress, '45%%') as progress
                FROM {DB_SCHEMA}.risk_treatment t
                JOIN {DB_SCHEMA}.risk_register r ON t.risk_register_id = r.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.mst_users u ON t.action_owner_id = u.id
                LEFT JOIN {DB_SCHEMA}.mst_status s ON t.action_status_id = s.id
                WHERE (t.is_deleted = 0 OR t.is_deleted IS NULL)
            """
            params = []
            if dept_id:
                query += " AND r.dept_id = %s"
                params.append(dept_id)
                
            query += " ORDER BY t.target_date ASC NULLS LAST LIMIT %s;"
            params.append(limit)
            
            cur.execute(query, params)
            results = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Error fetching overdue actions: {e}")
            return []

    def get_department_risk_summary(self, dept_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get aggregate count of risks per department."""
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = f"""
                SELECT 
                    COALESCE(d.dept_name, 'Unassigned') as department,
                    COUNT(r.risk_register_id) as total_risks,
                    COUNT(CASE WHEN r.risk_status IN (1, 2) THEN 1 END) as pending_fh_risks,
                    COUNT(CASE WHEN r.risk_status IN (3, 4) THEN 1 END) as pending_exec_risks,
                    COUNT(CASE WHEN r.risk_status = 5 THEN 1 END) as fully_approved_risks
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                WHERE r.is_deleted = 0
            """
            params = []
            if dept_id:
                query += " AND r.dept_id = %s"
                params.append(dept_id)
                
            query += " GROUP BY d.dept_name ORDER BY total_risks DESC;"
            cur.execute(query, params)
            results = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Error fetching department risk summary: {e}")
            return []

    def get_historical_treatments(self, keyword: str = "", dept_id: Optional[int] = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Fetch similar historical risk treatments to use as in-context recommendations."""
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            query = f"""
                SELECT 
                    t.risk_treatment_id as id,
                    t.risk_id,
                    r.risk_name,
                    t.action_plan,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Action Owner') as action_owner,
                    COALESCE(s.status_name, 'Completed') as status
                FROM {DB_SCHEMA}.risk_treatment t
                LEFT JOIN {DB_SCHEMA}.risk_register r ON t.risk_register_id = r.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_users u ON t.action_owner_id = u.id
                LEFT JOIN {DB_SCHEMA}.mst_status s ON t.action_status_id = s.id
                WHERE (t.is_deleted = 0 OR t.is_deleted IS NULL)
            """
            params = []
            if keyword:
                query += " AND (t.action_plan ILIKE %s OR r.risk_name ILIKE %s)"
                params.extend([f"%{keyword}%", f"%{keyword}%"])
            if dept_id:
                query += " AND r.dept_id = %s"
                params.append(dept_id)
                
            query += " LIMIT %s;"
            params.append(limit)
            cur.execute(query, params)
            results = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in results]
        except Exception as e:
            logger.error(f"Error fetching historical treatments: {e}")
            return []

    @staticmethod
    def score_candidate_match(
        draft_title: str,
        rec_title: Optional[str] = None,
        draft_desc: Optional[str] = None,
        rec_desc: Optional[str] = None,
        cand_title: Optional[str] = None,
        cand_desc: Optional[str] = None,
    ) -> Tuple[Optional[str], float]:
        """
        Evaluate deterministic similarity between a draft risk and an existing risk record.
        Returns (match_reason, similarity_score).
        """
        target_title = rec_title if rec_title is not None else cand_title
        target_desc = rec_desc if rec_desc is not None else cand_desc

        cleaned_draft = str(draft_title or "").strip()
        cleaned_rec = str(target_title or "").strip()
        if not cleaned_draft or not cleaned_rec:
            return None, 0.0

        STOP_WORDS = {
            "the", "a", "an", "at", "for", "in", "on", "of", "and", "or", "to",
            "with", "by", "from", "is", "are", "risk", "new", "potential", "due",
            "issue", "problem", "general", "hazard", "incident"
        }
        GENERIC_DESCRIPTIONS = {
            "operational risk", "process issue", "equipment failure",
            "general operational risk", "system issue", "safety issue", "routine issue"
        }

        def normalize_text(text: str) -> str:
            no_punc = re.sub(r'[^\w\s]', ' ', str(text or "").lower())
            return " ".join(no_punc.split())

        def get_tokens(text: str) -> Set[str]:
            norm = normalize_text(text)
            return {w for w in norm.split() if len(w) >= 3 and w not in STOP_WORDS}

        norm_draft = normalize_text(cleaned_draft)
        norm_rec = normalize_text(cleaned_rec)

        # Layer A: Exact or Normalized Name Match
        # Handle whitespace and case-insensitive equality
        if " ".join(cleaned_draft.lower().split()) == " ".join(cleaned_rec.lower().split()):
            return "exact_name_match", 1.0
        if norm_draft == norm_rec:
            return "normalized_name_match", 0.95

        draft_tokens = get_tokens(cleaned_draft)
        rec_tokens = get_tokens(cleaned_rec)
        intersection = draft_tokens & rec_tokens
        union = draft_tokens | rec_tokens

        jaccard = len(intersection) / len(union) if union else 0.0
        seq_ratio = SequenceMatcher(None, norm_draft, norm_rec).ratio()
        min_tokens = min(len(draft_tokens), len(rec_tokens))
        containment = (len(intersection) / min_tokens) if min_tokens >= 2 else 0.0

        # Layer B: Similar Name Match
        if jaccard >= 0.50 or containment >= 0.75 or seq_ratio >= 0.70:
            score = round(max(jaccard, seq_ratio, containment * 0.85), 2)
            return "similar_name", score

        # Layer C: Name and Description Similarity
        norm_draft_desc = normalize_text(draft_desc)
        norm_rec_desc = normalize_text(target_desc)
        is_meaningful_desc = (
            len(norm_draft_desc) >= 20
            and norm_draft_desc not in GENERIC_DESCRIPTIONS
            and len(norm_rec_desc) >= 15
        )

        if len(intersection) >= 1 and is_meaningful_desc:
            draft_desc_tokens = get_tokens(draft_desc)
            rec_desc_tokens = get_tokens(target_desc)
            desc_intersection = draft_desc_tokens & rec_desc_tokens
            if len(desc_intersection) >= 3:
                score = round(0.50 + min(0.30, len(desc_intersection) * 0.06), 2)
                return "name_and_description_similarity", score

        return None, 0.0

    def find_potential_duplicate_risks(
        self,
        risk_name: str,
        risk_description: Optional[str] = None,
        dept_id: Optional[int] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Identify potential duplicate risks across active risk register records using
        deterministic, explainable multi-layer matching.
        """
        cleaned_title = str(risk_name or "").strip()
        if len(cleaned_title) < 3:
            return []

        def normalize_text(text: str) -> str:
            no_punc = re.sub(r'[^\w\s]', ' ', str(text or "").lower())
            return " ".join(no_punc.split())

        def get_tokens(text: str) -> Set[str]:
            norm = normalize_text(text)
            STOP_WORDS = {
                "the", "a", "an", "at", "for", "in", "on", "of", "and", "or", "to",
                "with", "by", "from", "is", "are", "risk", "new", "potential", "due"
            }
            return {w for w in norm.split() if len(w) >= 3 and w not in STOP_WORDS}

        draft_tokens = get_tokens(cleaned_title)
        conn = None
        try:
            conn = self._get_connection()
            if not conn:
                return []
            cur = conn.cursor(cursor_factory=RealDictCursor)

            query = f"""
                SELECT 
                    r.risk_register_id as id,
                    r.risk_id,
                    r.risk_name,
                    r.dept_id,
                    COALESCE(d.dept_name, 'Enterprise') as dept_name,
                    r.risk_status,
                    COALESCE(s.status_name, 'Draft') as status_name,
                    COALESCE(rd.risk_description, '') as description
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.risk_description rd ON r.risk_register_id = rd.risk_register_id AND (rd.is_deleted = 0 OR rd.is_deleted IS NULL)
                LEFT JOIN {DB_SCHEMA}.mst_status s ON r.risk_status = s.id
                WHERE (r.is_deleted = 0 OR r.is_deleted IS NULL)
            """
            params: List[Any] = []
            if dept_id is not None:
                query += " AND r.dept_id = %s"
                params.append(dept_id)

            search_tokens = sorted(draft_tokens, key=lambda t: (-len(t), t))[:4]
            if search_tokens:
                token_clauses = ["r.risk_name ILIKE %s" for _ in search_tokens]
                query += f" AND ({' OR '.join(token_clauses)})"
                params.extend([f"%{t}%" for t in search_tokens])
            else:
                query += " AND r.risk_name ILIKE %s"
                params.append(f"%{cleaned_title[:20]}%")

            query += " ORDER BY r.risk_register_id DESC LIMIT 50;"

            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            candidates: List[Dict[str, Any]] = []
            for row in rows:
                rec_name = str(row.get("risk_name") or "")
                rec_desc = str(row.get("description") or "")

                match_reason, sim_score = self.score_candidate_match(
                    draft_title=cleaned_title,
                    rec_title=rec_name,
                    draft_desc=risk_description,
                    rec_desc=rec_desc
                )

                if match_reason and sim_score >= 0.50:
                    candidates.append({
                        "risk_id": row.get("risk_id"),
                        "risk_name": rec_name,
                        "dept_id": row.get("dept_id"),
                        "dept_name": row.get("dept_name"),
                        "status_name": row.get("status_name", "Draft"),
                        "match_reason": match_reason,
                        "similarity_score": sim_score,
                    })

            candidates.sort(key=lambda x: x["similarity_score"], reverse=True)
            return candidates[:limit]

        except Exception as e:
            logger.error(f"Error querying potential duplicate risks: {e}", exc_info=True)
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            return []

    def get_department_action_owners(self, dept_id: Optional[int] = None, dept_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Fetch users strictly in the same department whose role is Action Owner."""
        conn = self._get_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            resolved_dept_id = int(dept_id) if dept_id and str(dept_id).isdigit() else 1
            
            query = f"""
                SELECT 
                    u.id as user_id,
                    u.log_id,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id) as full_name,
                    u.email,
                    u.dept_id,
                    COALESCE(d.dept_name, 'General') as dept_name,
                    COALESCE(ut.name, 'Action Owner') as role_name
                FROM {DB_SCHEMA}.mst_users u
                LEFT JOIN {DB_SCHEMA}.mst_department d ON u.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                WHERE u.is_deleted = 0 AND u.dept_id = %s 
                  AND (ut.name ILIKE '%%action owner%%' OR u.user_type_id = 3 OR u.log_id ILIKE '%%_ao%%')
                ORDER BY u.id ASC;
            """
            cur.execute(query, [resolved_dept_id])
            rows = cur.fetchall()
            
            if not rows:
                fallback_query = f"""
                    SELECT 
                        u.id as user_id,
                        u.log_id,
                        COALESCE(u.first_name || ' ' || u.last_name, u.log_id) as full_name,
                        u.email,
                        u.dept_id,
                        COALESCE(d.dept_name, 'General') as dept_name,
                        COALESCE(ut.name, 'Action Owner') as role_name
                    FROM {DB_SCHEMA}.mst_users u
                    LEFT JOIN {DB_SCHEMA}.mst_department d ON u.dept_id = d.id
                    LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                    WHERE u.is_deleted = 0 AND u.dept_id = %s
                    ORDER BY u.id ASC LIMIT 5;
                """
                cur.execute(fallback_query, [resolved_dept_id])
                rows = cur.fetchall()

            cur.close()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching department action owners: {e}", exc_info=True)
            if conn:
                conn.close()
            return []

    def get_all_users_for_co_owner(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetch all active personnel across the organization for Co-Risk Owner selection."""
        conn = self._get_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            query = f"""
                SELECT 
                    u.id as user_id,
                    u.log_id,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id) as full_name,
                    u.email,
                    u.dept_id,
                    COALESCE(d.dept_name, 'Enterprise') as dept_name,
                    CASE 
                        WHEN u.log_id ILIKE '%%risk_head%%' THEN 'Risk Head'
                        WHEN u.log_id ILIKE '%%risk_manager%%' THEN 'Risk Manager'
                        WHEN u.log_id ILIKE '%%_fh%%' THEN 'Functional Head'
                        WHEN u.log_id ILIKE '%%_ro%%' THEN 'Risk Owner'
                        WHEN u.log_id ILIKE '%%_ao%%' THEN 'Action Owner'
                        ELSE COALESCE(ut.name, 'User')
                    END as role_name
                FROM {DB_SCHEMA}.mst_users u
                LEFT JOIN {DB_SCHEMA}.mst_department d ON u.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                WHERE u.is_deleted = 0
                ORDER BY u.dept_id ASC, u.id ASC LIMIT %s;
            """
            cur.execute(query, [limit])
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching co-owner users: {e}", exc_info=True)
            if conn:
                conn.close()
            return []

    def resolve_user_by_name_or_role(self, query_str: str, dept_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Resolve a user name or role mentioned in prompt to database user record."""
        if not query_str:
            return None
        try:
            conn = self._get_connection()
            cur = conn.cursor(cursor_factory=RealDictCursor)
            cur.execute(f"""
                SELECT 
                    u.id as user_id,
                    u.log_id,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id) as full_name,
                    u.dept_id,
                    COALESCE(d.dept_name, 'General') as department_name,
                    COALESCE(ut.name, 'Staff') as role_name
                FROM {DB_SCHEMA}.mst_users u
                LEFT JOIN {DB_SCHEMA}.mst_department d ON u.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                WHERE (
                    u.log_id ILIKE %s OR 
                    u.first_name ILIKE %s OR 
                    u.last_name ILIKE %s OR 
                    (u.first_name || ' ' || u.last_name) ILIKE %s OR
                    ut.name ILIKE %s
                )
                ORDER BY (u.dept_id = %s) DESC, u.id ASC
                LIMIT 1;
            """, (
                f"%{query_str}%", f"%{query_str}%", f"%{query_str}%", 
                f"%{query_str}%", f"%{query_str}%", dept_id or 1
            ))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error resolving user: {e}")
            return None

    def create_risk(
        self,
        risk_name: str,
        risk_description: str,
        dept_id: Optional[int] = None,
        dept_name: Optional[str] = None,
        risk_owner_id: Optional[Any] = None,
        risk_co_owner_id: Optional[Any] = None,
        inherent_likelihood: int = 4,
        inherent_impact: int = 4,
        current_likelihood: int = 2,
        current_impact: int = 2,
        mitigation: str = "",
        status: int = 1,
        financial_year: str = "2026-2027",
        treatments: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create and persist a new risk record into PostgreSQL MassERS."""
        now_str = datetime.now().isoformat()
        try:
            conn = self._get_connection(readonly=False)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            resolved_dept_id = int(dept_id) if dept_id and str(dept_id).isdigit() else 1
            resolved_dept_name = dept_name or "Refining"
            resolved_owner_id = int(risk_owner_id) if risk_owner_id and str(risk_owner_id).isdigit() else 5
            resolved_co_owner_id = int(risk_co_owner_id) if risk_co_owner_id and str(risk_co_owner_id).isdigit() else None
            resolved_status_id = int(status) if status and str(status).isdigit() else 1

            cur.execute(f"SELECT COALESCE(MAX(risk_register_id), 0) + 1 AS next_id FROM {DB_SCHEMA}.risk_register;")
            next_reg_id = cur.fetchone()["next_id"]
            dept_code = "REF"
            if resolved_dept_name:
                dept_code = "".join([c for c in resolved_dept_name[:3] if c.isalpha()]).upper() or "REF"
            generated_risk_id = f"RSK-{dept_code}-{next_reg_id:03d}"

            cur.execute(f"""
                INSERT INTO {DB_SCHEMA}.risk_register (
                    risk_register_id, risk_id, risk_name, dept_id, risk_owner_id, risk_co_owner_id, financial_year,
                    risk_status, created_by, created_on, modified_by, modified_on, is_active, is_deleted
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, '1', 0);
            """, (
                next_reg_id, generated_risk_id, risk_name[:250], resolved_dept_id, resolved_owner_id,
                resolved_co_owner_id, financial_year, resolved_status_id, resolved_owner_id, now_str,
                resolved_owner_id, now_str
            ))

            cur.execute(f"SELECT COALESCE(MAX(risk_description_id), 0) + 1 AS next_id FROM {DB_SCHEMA}.risk_description;")
            next_desc_id = cur.fetchone()["next_id"]

            cur.execute(f"""
                INSERT INTO {DB_SCHEMA}.risk_description (
                    risk_description_id, risk_register_id, risk_description, mitigation,
                    inherent_risk_likelihood_id, inherent_risk_impact_id,
                    current_risk_likelihood_id, current_risk_impact_id,
                    created_by, created_on, modified_by, modified_on, is_deleted
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0);
            """, (
                next_desc_id, next_reg_id, risk_description, mitigation, inherent_likelihood,
                inherent_impact, current_likelihood, current_impact, resolved_owner_id, now_str,
                resolved_owner_id, now_str
            ))

            inserted_treatments = []
            if treatments and isinstance(treatments, list):
                for t_item in treatments:
                    cur.execute(f"SELECT COALESCE(MAX(risk_treatment_id), 0) + 1 AS next_id FROM {DB_SCHEMA}.risk_treatment;")
                    next_treat_id = cur.fetchone()["next_id"]
                    action_text = t_item.get("action_plan") if isinstance(t_item, dict) else str(t_item)
                    target_ao_id = t_item.get("action_owner_id") if isinstance(t_item, dict) else resolved_owner_id
                    t_date = t_item.get("target_date") if isinstance(t_item, dict) else None
                    t_progress = t_item.get("progress") if isinstance(t_item, dict) else 0

                    if t_date:
                        cur.execute(f"""
                            INSERT INTO {DB_SCHEMA}.risk_treatment (
                                risk_treatment_id, risk_description_id, risk_register_id, risk_id, action_plan,
                                action_owner_id, target_date, progress, created_by, created_on, modified_by, modified_on, is_deleted
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 0);
                        """, (
                            next_treat_id, next_desc_id, next_reg_id, generated_risk_id, action_text,
                            target_ao_id, str(t_date), int(t_progress or 0), resolved_owner_id, now_str, resolved_owner_id, now_str
                        ))
                    else:
                        cur.execute(f"""
                            INSERT INTO {DB_SCHEMA}.risk_treatment (
                                risk_treatment_id, risk_description_id, risk_register_id, risk_id, action_plan,
                                action_owner_id, target_date, progress, created_by, created_on, modified_by, modified_on, is_deleted
                            ) VALUES (%s, %s, %s, %s, %s, %s, NOW() + INTERVAL '30 days', %s, %s, %s, %s, %s, 0);
                        """, (
                            next_treat_id, next_desc_id, next_reg_id, generated_risk_id, action_text,
                            target_ao_id, int(t_progress or 0), resolved_owner_id, now_str, resolved_owner_id, now_str
                        ))
                    inserted_treatments.append(action_text)

            cur.close()
            conn.close()

            return {
                "status": "success",
                "risk_id": generated_risk_id,
                "risk_register_id": next_reg_id,
                "risk_name": risk_name,
                "department_id": resolved_dept_id,
                "department_name": resolved_dept_name,
                "risk_status": status,
                "status_label": "Draft" if status == 1 else "Submitted to Functional Head",
                "inherent_likelihood": inherent_likelihood,
                "inherent_impact": inherent_impact,
                "inherent_score": inherent_likelihood * inherent_impact,
                "current_likelihood": current_likelihood,
                "current_impact": current_impact,
                "current_score": current_likelihood * current_impact,
                "created_on": now_str,
                "treatments": inserted_treatments
            }
        except Exception as e:
            logger.error(f"Error creating risk in database: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def get_treatments_for_risk(self, risk_ident: Any, dept_id: Optional[int] = None) -> List[Dict[str, Any]]:
        """Fetch all action plans / treatments for a specific risk by Risk ID or Register ID."""
        conn = self._get_connection()
        if not conn:
            return []
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            ident_str = str(risk_ident).strip()
            
            query = f"""
                SELECT 
                    t.risk_treatment_id,
                    t.risk_register_id,
                    t.risk_description_id,
                    t.risk_id,
                    r.risk_name,
                    t.action_plan,
                    t.action_owner_id,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Unassigned') AS action_owner_name,
                    u.email AS action_owner_email,
                    t.target_date,
                    COALESCE(t.progress, '0') AS progress,
                    t.action_status_id,
                    COALESCE(s.status_name, 'In Progress') AS action_status_name,
                    t.next_followup_date,
                    t.approval_status,
                    t.approval_remark,
                    t.created_on
                FROM {DB_SCHEMA}.risk_treatment t
                JOIN {DB_SCHEMA}.risk_register r ON t.risk_register_id = r.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_users u ON t.action_owner_id = u.id
                LEFT JOIN {DB_SCHEMA}.mst_status s ON t.action_status_id = s.id
                WHERE t.is_deleted = 0
                  AND (r.risk_id ILIKE %s OR r.risk_register_id::text = %s OR r.risk_name ILIKE %s)
            """
            params = [ident_str, ident_str, f"%{ident_str}%"]
            if dept_id:
                query += " AND (r.dept_id = %s OR %s IS NULL)"
                params.extend([dept_id, dept_id])

            query += " ORDER BY t.risk_treatment_id ASC;"
            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.error(f"Error fetching treatments for risk '{risk_ident}': {e}", exc_info=True)
            if conn:
                conn.close()
            return []

    def get_treatment_by_id(self, treatment_id: int) -> Optional[Dict[str, Any]]:
        """Fetch a single treatment record by its primary key with joined risk and user info."""
        conn = self._get_connection()
        if not conn:
            return None
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            query = f"""
                SELECT 
                    t.risk_treatment_id,
                    t.risk_register_id,
                    t.risk_description_id,
                    t.risk_id,
                    r.risk_name,
                    r.dept_id,
                    t.action_plan,
                    t.action_owner_id,
                    COALESCE(u.first_name || ' ' || u.last_name, u.log_id, 'Unassigned') AS action_owner_name,
                    u.email AS action_owner_email,
                    t.target_date,
                    COALESCE(t.progress, '0') AS progress,
                    t.action_status_id,
                    COALESCE(s.status_name, 'In Progress') AS action_status_name,
                    t.created_on
                FROM {DB_SCHEMA}.risk_treatment t
                JOIN {DB_SCHEMA}.risk_register r ON t.risk_register_id = r.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_users u ON t.action_owner_id = u.id
                LEFT JOIN {DB_SCHEMA}.mst_status s ON t.action_status_id = s.id
                WHERE t.risk_treatment_id = %s AND t.is_deleted = 0;
            """
            cur.execute(query, (treatment_id,))
            row = cur.fetchone()
            cur.close()
            conn.close()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Error fetching treatment #{treatment_id}: {e}", exc_info=True)
            if conn:
                conn.close()
            return None

    def add_risk_treatment(
        self,
        risk_register_id: int,
        action_plan: str,
        action_owner_id: int,
        target_date: Optional[str] = None,
        progress: int = 0,
        action_status_id: int = 1,
        created_by: int = 1
    ) -> Dict[str, Any]:
        """Add and persist a new treatment / action plan to an existing risk."""
        now_str = datetime.now().isoformat()
        try:
            conn = self._get_connection(readonly=False)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            # 1. Fetch risk details
            cur.execute(f"""
                SELECT r.risk_register_id, r.risk_id, r.risk_name, r.dept_id, rd.risk_description_id
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.risk_description rd ON r.risk_register_id = rd.risk_register_id
                WHERE r.risk_register_id = %s AND r.is_deleted = 0;
            """, (risk_register_id,))
            risk_row = cur.fetchone()
            if not risk_row:
                cur.close()
                conn.close()
                return {"status": "error", "message": f"Risk Register #{risk_register_id} not found."}

            # Ensure created_by is integer or fallback to 1
            created_by_int = int(created_by) if str(created_by).isdigit() else 1

            desc_id = risk_row.get("risk_description_id")
            if not desc_id:
                # If no description exists, find or create one
                cur.execute(f"SELECT COALESCE(MAX(risk_description_id), 0) + 1 AS next_id FROM {DB_SCHEMA}.risk_description;")
                desc_id = cur.fetchone()["next_id"]
                cur.execute(f"""
                    INSERT INTO {DB_SCHEMA}.risk_description (
                        risk_description_id, risk_register_id, risk_description, created_by, created_on, is_deleted
                    ) VALUES (%s, %s, %s, %s, %s, 0);
                """, (desc_id, risk_register_id, risk_row["risk_name"], created_by_int, now_str))

            # 2. Get next treatment ID
            cur.execute(f"SELECT COALESCE(MAX(risk_treatment_id), 0) + 1 AS next_id FROM {DB_SCHEMA}.risk_treatment;")
            next_t_id = cur.fetchone()["next_id"]

            t_date_sql = f"'{target_date}'" if target_date else "NOW() + INTERVAL '30 days'"

            cur.execute(f"""
                INSERT INTO {DB_SCHEMA}.risk_treatment (
                    risk_treatment_id, risk_description_id, risk_register_id, risk_id,
                    action_plan, action_owner_id, target_date, progress, action_status_id,
                    created_by, created_on, modified_by, modified_on, is_deleted
                ) VALUES (%s, %s, %s, %s, %s, %s, {t_date_sql}, %s, %s, %s, %s, %s, %s, 0);
            """, (
                next_t_id, desc_id, risk_register_id, risk_row.get("risk_id"),
                action_plan.strip(), action_owner_id, str(progress), action_status_id,
                created_by_int, now_str, created_by_int, now_str
            ))

            # 3. If risk was in draft (1), rejected/revision (6 or 3), or being updated by RO, reset approval statuses to NULL and advance to Stage 1 (FH)
            current_r_status = risk_row.get("risk_status")
            if current_r_status in [1, 3, 6] or current_r_status is not None:
                cur.execute(f"""
                    UPDATE {DB_SCHEMA}.risk_register
                    SET 
                        risk_status = 2,
                        risk_function_head_approval_status = NULL,
                        risk_function_head_approval_by = NULL,
                        risk_function_head_approval_on = NULL,
                        risk_function_head_approval_remark = NULL,
                        risk_manager_approval_status = NULL,
                        risk_manager_approval_by = NULL,
                        risk_manager_approved_on = NULL,
                        risk_manager_approval_remark = NULL,
                        risk_head_approval_status = NULL,
                        risk_head_approval_by = NULL,
                        risk_head_approved_on = NULL,
                        risk_head_approval_remark = NULL,
                        modified_by = %s,
                        modified_on = %s
                    WHERE risk_register_id = %s;
                """, (created_by_int, now_str, risk_register_id))

                # Insert into risk_register_hist
                try:
                    cur.execute(f"""
                        INSERT INTO {DB_SCHEMA}.risk_register_hist (
                            risk_register_id, risk_id, risk_name, dept_id, risk_owner_id, risk_co_owner_id,
                            financial_year, risk_status, risk_progress,
                            risk_function_head_approval_status, risk_function_head_approval_remark,
                            risk_function_head_approval_on, risk_function_head_approval_by,
                            risk_manager_approval_status, risk_manager_approval_remark,
                            risk_manager_approved_on, risk_manager_approval_by,
                            risk_head_approval_status, risk_head_approval_remark,
                            risk_head_approved_on, risk_head_approval_by,
                            created_by, created_on, modified_by, modified_on, is_active, is_deleted
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            NULL, %s,
                            NULL, NULL,
                            NULL, NULL,
                            NULL, NULL,
                            NULL, NULL,
                            NULL, NULL,
                            %s, %s, %s, %s, %s, %s
                        );
                    """, (
                        risk_register_id, risk_row.get("risk_id"), risk_row.get("risk_name"), risk_row.get("dept_id"),
                        risk_row.get("risk_owner_id"), risk_row.get("risk_co_owner_id"),
                        risk_row.get("financial_year"), 2, risk_row.get("risk_progress"),
                        f"Action plan #{next_t_id} added. Previous approval decisions reset to NULL and resubmitted to Functional Head.",
                        risk_row.get("created_by") or created_by_int, risk_row.get("created_on") or now_str,
                        created_by_int, now_str, risk_row.get("is_active", 1), 0
                    ))
                except Exception as hist_err:
                    logger.warning(f"Could not record risk history on treatment add: {hist_err}")

            # 4. Fetch Action Owner Name
            cur.execute(f"SELECT COALESCE(first_name || ' ' || last_name, log_id) AS full_name FROM {DB_SCHEMA}.mst_users WHERE id = %s;", (action_owner_id,))
            ao_row = cur.fetchone()
            ao_name = ao_row["full_name"] if ao_row else "Action Owner"

            cur.close()
            conn.close()

            return {
                "status": "success",
                "risk_treatment_id": next_t_id,
                "risk_register_id": risk_register_id,
                "risk_id": risk_row.get("risk_id"),
                "risk_name": risk_row.get("risk_name"),
                "action_plan": action_plan,
                "action_owner_id": action_owner_id,
                "action_owner_name": ao_name,
                "target_date": target_date or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                "progress": progress,
                "created_on": now_str,
                "risk_status": 2,
                "status_reset": True
            }
        except Exception as e:
            logger.error(f"Error adding risk treatment: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def update_treatment_progress(
        self,
        treatment_id: int,
        progress: int,
        modified_by: int = 1,
        remarks: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update progress percentage and completion status for a specific risk treatment."""
        now_str = datetime.now().isoformat()
        try:
            conn = self._get_connection(readonly=False)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            new_status_id = 8 if progress >= 100 else (7 if progress > 0 else 1)

            cur.execute(f"""
                UPDATE {DB_SCHEMA}.risk_treatment
                SET progress = %s, action_status_id = %s, modified_by = %s, modified_on = %s
                WHERE risk_treatment_id = %s AND is_deleted = 0
                RETURNING risk_treatment_id, risk_register_id, risk_id, action_plan, action_owner_id, target_date, progress, action_status_id;
            """, (str(progress), new_status_id, modified_by, now_str, treatment_id))

            updated = cur.fetchone()
            cur.close()
            conn.close()

            if not updated:
                return {"status": "error", "message": f"Treatment #{treatment_id} not found."}

            return {
                "status": "success",
                "risk_treatment_id": updated["risk_treatment_id"],
                "risk_id": updated["risk_id"],
                "action_plan": updated["action_plan"],
                "progress": updated["progress"],
                "action_status_id": updated["action_status_id"],
                "status_label": "Completed" if progress >= 100 else ("In Progress" if progress > 0 else "Draft"),
                "modified_on": now_str
            }
        except Exception as e:
            logger.error(f"Error updating treatment progress #{treatment_id}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def reassign_treatment_owner(
        self,
        treatment_id: int,
        new_action_owner_id: int,
        modified_by: int = 1
    ) -> Dict[str, Any]:
        """Reassign designated Action Owner for a specific treatment."""
        now_str = datetime.now().isoformat()
        try:
            conn = self._get_connection(readonly=False)
            cur = conn.cursor(cursor_factory=RealDictCursor)

            cur.execute(f"""
                UPDATE {DB_SCHEMA}.risk_treatment
                SET action_owner_id = %s, modified_by = %s, modified_on = %s
                WHERE risk_treatment_id = %s AND is_deleted = 0
                RETURNING risk_treatment_id, risk_register_id, risk_id, action_plan, action_owner_id;
            """, (new_action_owner_id, modified_by, now_str, treatment_id))

            updated = cur.fetchone()
            if not updated:
                cur.close()
                conn.close()
                return {"status": "error", "message": f"Treatment #{treatment_id} not found."}

            cur.execute(f"SELECT COALESCE(first_name || ' ' || last_name, log_id) AS full_name FROM {DB_SCHEMA}.mst_users WHERE id = %s;", (new_action_owner_id,))
            ao_row = cur.fetchone()
            ao_name = ao_row["full_name"] if ao_row else "Action Owner"

            cur.close()
            conn.close()

            return {
                "status": "success",
                "risk_treatment_id": updated["risk_treatment_id"],
                "risk_id": updated["risk_id"],
                "action_plan": updated["action_plan"],
                "action_owner_id": new_action_owner_id,
                "action_owner_name": ao_name,
                "modified_on": now_str
            }
        except Exception as e:
            logger.error(f"Error reassigning treatment owner #{treatment_id}: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def get_status_options(self, status_type: str = "risk") -> List[Dict[str, Any]]:
        """Fetch available governance risk/action statuses from master tables."""
        conn = self._get_connection()
        if not conn:
            return [
                {"id": 1, "status_name": "Draft", "type": "RISK"},
                {"id": 2, "status_name": "Submitted to Functional Head", "type": "RISK"}
            ]
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            type_str = str(status_type).lower() if status_type else "risk"
            if type_str in ["risk", "approval"]:
                cur.execute(f"""
                    SELECT id, status_name, type 
                    FROM {DB_SCHEMA}.mst_status 
                    WHERE is_deleted = 0 AND UPPER(type) IN ('RISK', 'APPROVAL')
                    ORDER BY id ASC;
                """)
            elif type_str in ["action", "treatment", "action_plan"]:
                cur.execute(f"""
                    SELECT id, status_name, type 
                    FROM {DB_SCHEMA}.mst_status 
                    WHERE is_deleted = 0 AND (UPPER(type) IN ('ACTION', 'RISK') OR id IN (1, 7, 8))
                    ORDER BY id ASC;
                """)
            else:
                cur.execute(f"""
                    SELECT id, status_name, type 
                    FROM {DB_SCHEMA}.mst_status 
                    WHERE is_deleted = 0
                    ORDER BY id ASC;
                """)
            rows = cur.fetchall()
            cur.close()
            conn.close()
            return [dict(r) for r in rows] if rows else [
                {"id": 1, "status_name": "Draft", "type": "RISK"},
                {"id": 2, "status_name": "Submitted to Functional Head", "type": "RISK"}
            ]
        except Exception as e:
            logger.error(f"Error fetching status options: {e}")
            if conn:
                conn.close()
            return [
                {"id": 1, "status_name": "Draft", "type": "RISK"},
                {"id": 2, "status_name": "Submitted to Functional Head", "type": "RISK"}
            ]

    def resolve_status_by_name(self, query_str: str) -> Optional[Dict[str, Any]]:
        """Resolve a user-provided status keyword to authoritative status master row."""
        if not query_str:
            return None
        lower = query_str.strip().lower()
        if any(w in lower for w in ["draft", "save as draft", "new", "1"]):
            return {"id": 1, "status_name": "Draft", "type": "RISK"}
        elif any(w in lower for w in ["submit", "functional head", "fh", "stage 2", "2"]):
            return {"id": 2, "status_name": "Submitted to Functional Head", "type": "RISK"}

        statuses = self.get_status_options("risk")
        for s in statuses:
            s_name = (s.get("status_name") or "").lower()
            if lower in s_name or s_name in lower or str(s.get("id")) == lower:
                return s
        return None

    def get_dropdown_options(self, dept_id: Optional[int] = None) -> Dict[str, Any]:
        """
        Fetch dropdown metadata options for departments, statuses, likelihood, impact, and action owners.
        Guarantees parameterized query execution, department scoping, and robust error handling.
        """
        from ERM_Copilot.agents.risk_creation.scoring import RiskMatrixCalculator

        likelihood_scales = [
            {"id": k, "name": v, "code": f"L{k}"}
            for k, v in RiskMatrixCalculator.LIKELIHOOD_LABELS.items()
        ]
        impact_scales = [
            {"id": k, "name": v, "code": f"I{k}"}
            for k, v in RiskMatrixCalculator.IMPACT_LABELS.items()
        ]

        departments: List[Dict[str, Any]] = []
        statuses: List[Dict[str, Any]] = []
        action_owners: List[Dict[str, Any]] = []

        try:
            conn = self._get_connection()
            if conn:
                try:
                    cur = conn.cursor(cursor_factory=RealDictCursor)
                    cur.execute(f"""
                        SELECT id, dept_name, dept_short_name 
                        FROM {DB_SCHEMA}.mst_department 
                        WHERE is_deleted = 0 
                        ORDER BY id ASC;
                    """)
                    dept_rows = cur.fetchall()
                    departments = [dict(r) for r in dept_rows]
                    cur.close()
                finally:
                    conn.close()
        except Exception as e:
            logger.error(f"Error fetching departments in get_dropdown_options: {e}")

        try:
            statuses = self.get_status_options(status_type="risk")
        except Exception as e:
            logger.error(f"Error fetching status options in get_dropdown_options: {e}")
            statuses = []

        if dept_id is not None:
            try:
                resolved_dept_id = int(dept_id) if str(dept_id).isdigit() else None
                if resolved_dept_id:
                    raw_owners = self.get_department_action_owners(dept_id=resolved_dept_id)
                    # Sanitize to prevent exposing sensitive personal data
                    action_owners = [
                        {
                            "user_id": ao.get("user_id"),
                            "log_id": ao.get("log_id"),
                            "full_name": ao.get("full_name"),
                            "dept_id": ao.get("dept_id"),
                            "dept_name": ao.get("dept_name"),
                            "role_name": ao.get("role_name", "Action Owner"),
                        }
                        for ao in raw_owners
                    ]
            except Exception as e:
                logger.error(f"Error fetching action owners in get_dropdown_options: {e}")
                action_owners = []

        return {
            "status": "success",
            "departments": departments,
            "statuses": statuses,
            "likelihood_scales": likelihood_scales,
            "impact_scales": impact_scales,
            "action_owners": action_owners,
        }


    def approve_or_reject_risk(
        self,
        risk_id: str,
        approver_id: int,
        action: str = "approve",
        remark: str = ""
    ) -> Dict[str, Any]:
        """
        Execute 1-Click Governance Sign-off (Approve / Reject).
        Determines role & stage automatically from authenticated database identity.
        Enforces strict FH -> RM -> RH approval sequence and preserves audit history.
        """
        # 1. Validate approver_id - NO FALLBACKS
        if approver_id is None:
            return {"success": False, "message": "Authentication required. Valid approver identity not found."}
        try:
            approver_id = int(approver_id)
            if approver_id <= 0:
                return {"success": False, "message": "Invalid approver identifier."}
        except (ValueError, TypeError):
            return {"success": False, "message": "Authentication error: Invalid approver identifier."}

        if not risk_id or not str(risk_id).strip():
            return {"success": False, "message": "A valid risk identifier is required."}

        conn = self._get_connection(readonly=False)
        if not conn:
            return {"success": False, "message": "Database connection failed."}

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            now_dt = datetime.now()
            now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

            # 2. Load authenticated user from DB to determine true role
            cur.execute(f"""
                SELECT u.id, u.log_id, u.first_name, u.last_name, u.email, u.dept_id, u.role_id, u.user_type_id,
                       COALESCE(ut.name, '') as user_type_name
                FROM {DB_SCHEMA}.mst_users u
                LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                WHERE u.id = %s AND (u.is_deleted = 0 OR u.is_deleted IS NULL);
            """, [approver_id])
            user_row = cur.fetchone()
            if not user_row:
                cur.close()
                conn.close()
                return {"success": False, "message": f"Authenticated user ID {approver_id} not found in database."}

            u_type_name = str(user_row.get("user_type_name") or "").lower().strip()
            u_log_id = str(user_row.get("log_id") or "").lower().strip()
            user_display_name = f"{user_row.get('first_name', '')} {user_row.get('last_name', '')}".strip() or user_row.get("log_id")

            # 3. Determine actual role and initial approval level from DB
            role_category = None
            approval_level = None
            role_title = None

            if "function" in u_type_name or "fh" in u_type_name or "_fh" in u_log_id or user_row.get("user_type_id") == 4:
                role_category = "FH"
                approval_level = 1
                role_title = "Functional Head"
            elif "risk manager" in u_type_name or "_rm" in u_log_id or "risk_manager" in u_log_id or (("manager" in u_type_name) and not ("function" in u_type_name)):
                role_category = "RM"
                approval_level = 2
                role_title = "Risk Manager"
            elif "risk head" in u_type_name or "cro" in u_type_name or "chief risk" in u_type_name or "_rh" in u_log_id or "risk_head" in u_log_id or ("head" in u_type_name and not "function" in u_type_name):
                role_category = "RH"
                approval_level = 3
                role_title = "Risk Head"
            elif "admin" in u_type_name or "admin" in u_log_id or user_row.get("user_type_id") == 1:
                role_category = "ADMIN"
                role_title = "Administrator"
            else:
                cur.close()
                conn.close()
                return {
                    "success": False,
                    "message": f"User '{user_display_name}' (Role: '{user_row.get('user_type_name') or 'User'}') is not authorized to approve or reject risks. Only Functional Head, Risk Manager, and Risk Head can perform governance sign-offs."
                }

            # 4. Load the risk record
            cur.execute(f"""
                SELECT 
                    r.risk_register_id, r.risk_id, r.risk_name, r.dept_id, r.risk_owner_id, r.risk_co_owner_id,
                    r.financial_year, r.risk_status, r.risk_progress,
                    r.risk_function_head_approval_status, r.risk_function_head_approval_by, r.risk_function_head_approval_on, r.risk_function_head_approval_remark,
                    r.risk_manager_approval_status, r.risk_manager_approval_by, r.risk_manager_approved_on, r.risk_manager_approval_remark,
                    r.risk_head_approval_status, r.risk_head_approval_by, r.risk_head_approved_on, r.risk_head_approval_remark,
                    r.created_by, r.created_on, r.modified_by, r.modified_on, r.is_active, r.is_deleted,
                    COALESCE(st.status_name, '') as current_status_name
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_status st ON r.risk_status = st.id
                WHERE (r.risk_id ILIKE %s OR r.risk_register_id::text = %s) AND (r.is_deleted = 0 OR r.is_deleted IS NULL)
                LIMIT 1;
            """, [risk_id.strip(), risk_id.strip()])
            risk_row = cur.fetchone()
            if not risk_row:
                cur.close()
                conn.close()
                return {"success": False, "message": f"Risk record '{risk_id}' not found."}

            reg_id = risk_row["risk_register_id"]
            r_title = risk_row["risk_name"]
            r_id_code = risk_row["risk_id"]

            fh_status = risk_row.get("risk_function_head_approval_status")
            rm_status = risk_row.get("risk_manager_approval_status")
            rh_status = risk_row.get("risk_head_approval_status")
            curr_status_name = str(risk_row.get("current_status_name") or "").lower()

            # 5. Check Draft & Rejection states
            if "draft" in curr_status_name or risk_row.get("risk_status") == 1:
                cur.close()
                conn.close()
                return {"success": False, "message": f"Risk '{r_id_code}' is currently in Draft status and has not been submitted for review."}

            if fh_status == -1 or rm_status == -1 or rh_status == -1 or "pending for action" in curr_status_name:
                cur.close()
                conn.close()
                return {"success": False, "message": f"Risk '{r_id_code}' has already been rejected/returned and must be modified and resubmitted by the Risk Owner before review can continue."}

            # 6. Evaluate stage completion status
            raw_r_status = risk_row.get("risk_status") or 0
            try:
                numeric_r_status = int(raw_r_status)
            except (ValueError, TypeError):
                numeric_r_status = 0

            fh_done = (fh_status == 1) or (numeric_r_status >= 3)
            rm_done = (rm_status == 1) or (numeric_r_status >= 4)
            rh_done = (rh_status == 1) or (numeric_r_status >= 5)

            # If Admin, determine the active approval level from the pending stage
            if role_category == "ADMIN":
                if not fh_done:
                    approval_level = 1
                    role_title = "Admin (Functional Head Stage)"
                elif not rm_done:
                    approval_level = 2
                    role_title = "Admin (Risk Manager Stage)"
                elif not rh_done:
                    approval_level = 3
                    role_title = "Admin (Risk Head Stage)"
                else:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": f"Risk '{r_id_code}' has already been fully approved at all governance stages."}

            # 7. Strict Governance Sequence & Department Isolation Enforcement
            if approval_level == 1:
                # Department Isolation for Functional Head (Fail Closed)
                u_dept = user_row.get("dept_id")
                r_dept = risk_row.get("dept_id")
                if u_dept is None or r_dept is None:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": f"Department isolation check failed: Missing department identifier for user or risk record '{r_id_code}'."}
                try:
                    if int(u_dept) != int(r_dept):
                        cur.close()
                        conn.close()
                        return {"success": False, "message": f"Department access restriction: User department ({u_dept}) does not match risk department ({r_dept}). Functional Head review is restricted to own department."}
                except (ValueError, TypeError):
                    cur.close()
                    conn.close()
                    return {"success": False, "message": "Department access restriction: Invalid department identifier format."}

                if fh_done and not (rm_done or rh_done):
                    cur.close()
                    conn.close()
                    return {"success": False, "message": f"Risk '{r_id_code}' has already been approved by Functional Head."}
            elif approval_level == 2:
                if not fh_done:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": "This risk is not yet available for Risk Manager approval. Functional Head approval is still pending."}
                if rm_done:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": f"Risk '{r_id_code}' has already been approved by Risk Manager."}
            elif approval_level == 3:
                if not fh_done:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": "This risk is not yet available for Risk Head approval. Functional Head approval is still pending."}
                if not rm_done:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": "This risk is not yet available for Risk Head approval. Risk Manager approval is still pending."}
                if rh_done:
                    cur.close()
                    conn.close()
                    return {"success": False, "message": f"Risk '{r_id_code}' has already been approved by Risk Head (Final Approval complete)."}

            # 8. Action & Remark Validation
            is_approve = str(action).strip().lower() in ["approve", "approved", "signoff", "sign-off", "accept", "yes"]
            is_reject = str(action).strip().lower() in ["reject", "rejected", "return", "returned", "no"]

            if not is_approve and not is_reject:
                cur.close()
                conn.close()
                return {"success": False, "message": f"Invalid action '{action}'. Action must be 'approve' or 'reject'."}

            remark_str = (remark or "").strip()
            if is_reject and not remark_str:
                cur.close()
                conn.close()
                return {"success": False, "message": "A rejection reason/remark is mandatory when rejecting a risk."}

            if not remark_str:
                remark_str = f"Approved by {role_title} via ERM Copilot"

            # 9. Resolve status IDs dynamically from DB
            cur.execute(f"SELECT id, status_name FROM {DB_SCHEMA}.mst_status WHERE is_deleted = 0;")
            status_rows = cur.fetchall()
            status_map = {str(s["status_name"]).lower().strip(): s["id"] for s in status_rows}
            pending_action_id = status_map.get("pending for action", 6)
            approved_status_id = status_map.get("approved", 5)

            new_fh_status = fh_status
            new_fh_by = risk_row.get("risk_function_head_approval_by")
            new_fh_on = risk_row.get("risk_function_head_approval_on")
            new_fh_remark = risk_row.get("risk_function_head_approval_remark")

            new_rm_status = rm_status
            new_rm_by = risk_row.get("risk_manager_approval_by")
            new_rm_on = risk_row.get("risk_manager_approved_on")
            new_rm_remark = risk_row.get("risk_manager_approval_remark")

            new_rh_status = rh_status
            new_rh_by = risk_row.get("risk_head_approval_by")
            new_rh_on = risk_row.get("risk_head_approved_on")
            new_rh_remark = risk_row.get("risk_head_approval_remark")

            if is_approve:
                if approval_level == 1:
                    new_fh_status = 1
                    new_fh_by = approver_id
                    new_fh_on = now_dt
                    new_fh_remark = remark_str
                    new_risk_status = status_map.get("opened", 3)
                    stage_name = "Stage 1: Functional Head Approval"
                    next_queue = "Stage 2: Risk Manager Validation Queue"
                elif approval_level == 2:
                    new_rm_status = 1
                    new_rm_by = approver_id
                    new_rm_on = now_dt
                    new_rm_remark = remark_str
                    new_risk_status = status_map.get("opened", 4)
                    stage_name = "Stage 2: Risk Manager Validation"
                    next_queue = "Stage 3: Risk Head Final Approval Queue"
                else: # approval_level == 3
                    new_rh_status = 1
                    new_rh_by = approver_id
                    new_rh_on = now_dt
                    new_rh_remark = remark_str
                    new_risk_status = approved_status_id
                    stage_name = "Stage 3: Risk Head Final Sign-Off"
                    next_queue = "Approved (Active Enterprise Risk Register)"
            else: # is_reject
                if approval_level == 1:
                    new_fh_status = -1
                    new_fh_by = approver_id
                    new_fh_on = now_dt
                    new_fh_remark = remark_str
                elif approval_level == 2:
                    new_rm_status = -1
                    new_rm_by = approver_id
                    new_rm_on = now_dt
                    new_rm_remark = remark_str
                else: # approval_level == 3
                    new_rh_status = -1
                    new_rh_by = approver_id
                    new_rh_on = now_dt
                    new_rh_remark = remark_str
                new_risk_status = pending_action_id
                stage_name = f"Stage {approval_level}: {role_title} Rejection"
                next_queue = "Returned to Risk Owner for Revision"

            # 10. Update risk_register
            cur.execute(f"""
                UPDATE {DB_SCHEMA}.risk_register
                SET risk_status = %s,
                    risk_function_head_approval_status = %s, risk_function_head_approval_by = %s,
                    risk_function_head_approval_on = %s, risk_function_head_approval_remark = %s,
                    risk_manager_approval_status = %s, risk_manager_approval_by = %s,
                    risk_manager_approved_on = %s, risk_manager_approval_remark = %s,
                    risk_head_approval_status = %s, risk_head_approval_by = %s,
                    risk_head_approved_on = %s, risk_head_approval_remark = %s,
                    modified_by = %s, modified_on = %s
                WHERE risk_register_id = %s;
            """, (
                new_risk_status,
                new_fh_status, new_fh_by, new_fh_on, new_fh_remark,
                new_rm_status, new_rm_by, new_rm_on, new_rm_remark,
                new_rh_status, new_rh_by, new_rh_on, new_rh_remark,
                approver_id, now_dt, reg_id
            ))

            # 11. Insert Audit History into risk_register_hist
            try:
                cur.execute(f"""
                    INSERT INTO {DB_SCHEMA}.risk_register_hist (
                        risk_register_id, risk_id, risk_name, dept_id, risk_owner_id, risk_co_owner_id,
                        financial_year, risk_status, risk_progress,
                        risk_function_head_approval_status, risk_function_head_approval_remark,
                        risk_function_head_approval_on, risk_function_head_approval_by,
                        risk_manager_approval_status, risk_manager_approval_remark,
                        risk_manager_approved_on, risk_manager_approval_by,
                        risk_head_approval_status, risk_head_approval_remark,
                        risk_head_approved_on, risk_head_approval_by,
                        created_by, created_on, modified_by, modified_on, is_active, is_deleted
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s,
                        %s, %s, %s, %s, %s, %s
                    );
                """, (
                    reg_id, r_id_code, r_title, risk_row.get("dept_id"), risk_row.get("risk_owner_id"), risk_row.get("risk_co_owner_id"),
                    risk_row.get("financial_year"), new_risk_status, risk_row.get("risk_progress"),
                    new_fh_status, new_fh_remark, new_fh_on, new_fh_by,
                    new_rm_status, new_rm_remark, new_rm_on, new_rm_by,
                    new_rh_status, new_rh_remark, new_rh_on, new_rh_by,
                    risk_row.get("created_by"), risk_row.get("created_on") or now_dt,
                    approver_id, now_dt, risk_row.get("is_active", 1), 0
                ))
            except Exception as hist_err:
                logger.warning(f"Could not insert risk history record: {hist_err}")

            conn.commit()
            cur.close()
            conn.close()

            # 12. Trigger Email Events if available (non-blocking post-commit)
            notification_status = "SENT"
            notification_error = None
            try:
                from ERM_API.app.core.database import SessionLocal
                from ERM_API.app.services.email_event_service import (
                    send_function_approval_email_seq,
                    send_risk_rejection_email,
                    send_treatment_email_after_approval
                )
                with SessionLocal() as db_session:
                    if is_approve:
                        send_function_approval_email_seq(db_session, reg_id, approval_level)
                        if new_fh_status == 1 and new_rm_status == 1 and new_rh_status == 1:
                            send_treatment_email_after_approval(db_session, reg_id)
                    else:
                        role_map = {1: "Functional Head", 2: "Risk Manager", 3: "Risk Head"}
                        send_risk_rejection_email(
                            db=db_session,
                            risk_register_id=reg_id,
                            rejected_by_role=role_map.get(approval_level, "Functional Head"),
                            remark=remark_str
                        )
            except Exception as mail_err:
                notification_status = "FAILED_OR_PENDING"
                notification_error = str(mail_err)
                logger.warning(f"Email notification dispatch skipped or encountered non-fatal error: {mail_err}")

            return {
                "success": True,
                "risk_id": r_id_code,
                "risk_register_id": reg_id,
                "risk_title": r_title,
                "action": "Approved" if is_approve else "Rejected",
                "stage": stage_name,
                "approval_level": approval_level,
                "approver_name": user_display_name,
                "approver_role": role_title,
                "next_queue": next_queue,
                "timestamp": now_str,
                "remark": remark_str,
                "notification_status": notification_status,
                "notification_error": notification_error,
            }
        except Exception as e:
            logger.error(f"Error executing approve_or_reject_risk: {e}", exc_info=True)
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            return {"success": False, "message": str(e)}

    def resubmit_risk(
        self,
        risk_id: str,
        user_id: int,
        remark: Optional[str] = "Modified and resubmitted by Risk Owner for approval"
    ) -> Dict[str, Any]:
        """
        Resubmit a draft or returned/rejected risk back into the Stage 1 Functional Head approval queue.
        Clears all previous FH, RM, and RH approval statuses, timestamps, approver IDs, and remarks (sets them to NULL).
        Updates risk_status to 2 ('Submitted to Functional Head') and records an immutable audit history entry.
        """
        if not risk_id or not str(risk_id).strip():
            return {"success": False, "message": "A valid Risk ID or Register ID is required."}

        if user_id is None:
            return {"success": False, "message": "Authentication required. User ID must be provided."}

        try:
            valid_user_id = int(user_id)
            if valid_user_id <= 0:
                return {"success": False, "message": "Invalid user ID."}
        except (ValueError, TypeError):
            return {"success": False, "message": f"Invalid user ID '{user_id}'."}

        conn = self._get_connection(readonly=False)
        if not conn:
            return {"success": False, "message": "Database connection unavailable."}

        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            
            # 1. Fetch user
            cur.execute(f"""
                SELECT u.id, u.log_id, u.first_name, u.last_name, u.email, u.dept_id,
                       COALESCE(u.first_name || ' ' || u.last_name, u.log_id) as full_name,
                       COALESCE(ut.name, 'User') as user_type_name
                FROM {DB_SCHEMA}.mst_users u
                LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                WHERE u.id = %s;
            """, (valid_user_id,))
            user_row = cur.fetchone()
            user_display_name = user_row["full_name"] if user_row else "Risk Owner"
            user_role = user_row.get("user_type_name", "Risk Owner") if user_row else "Risk Owner"

            # 2. Fetch risk record
            import re
            id_match = re.search(r'\b(RSK-[A-Z0-9]+-\d{1,4}|[A-Z]{2,5}-\d{1,5}|RSK-\d+)\b', str(risk_id), re.IGNORECASE)
            clean_id = id_match.group(1).upper() if id_match else str(risk_id).strip()

            cur.execute(f"""
                SELECT 
                    r.risk_register_id, r.risk_id, r.risk_name, r.dept_id, r.risk_owner_id, r.risk_co_owner_id,
                    r.financial_year, r.risk_status, r.risk_progress,
                    r.created_by, r.created_on, r.modified_by, r.modified_on, r.is_active, r.is_deleted,
                    COALESCE(st.status_name, '') as current_status_name
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.mst_status st ON r.risk_status = st.id
                WHERE (r.risk_id ILIKE %s OR r.risk_register_id::text = %s) AND (r.is_deleted = 0 OR r.is_deleted IS NULL)
                LIMIT 1;
            """, [clean_id, clean_id])
            risk_row = cur.fetchone()
            if not risk_row:
                cur.close()
                conn.close()
                return {"success": False, "message": f"Risk record '{risk_id}' not found."}

            reg_id = risk_row["risk_register_id"]
            r_title = risk_row["risk_name"]
            r_id_code = risk_row["risk_id"]

            now_dt = datetime.now()
            now_str = now_dt.strftime("%Y-%m-%d %H:%M:%S")

            # 3. Clear all previous FH, RM, and RH approval columns (NULL) and set status to 2 (Submitted to FH)
            cur.execute(f"""
                UPDATE {DB_SCHEMA}.risk_register
                SET 
                    risk_status = 2,
                    risk_function_head_approval_status = NULL,
                    risk_function_head_approval_by = NULL,
                    risk_function_head_approval_on = NULL,
                    risk_function_head_approval_remark = NULL,
                    risk_manager_approval_status = NULL,
                    risk_manager_approval_by = NULL,
                    risk_manager_approved_on = NULL,
                    risk_manager_approval_remark = NULL,
                    risk_head_approval_status = NULL,
                    risk_head_approval_by = NULL,
                    risk_head_approved_on = NULL,
                    risk_head_approval_remark = NULL,
                    modified_by = %s,
                    modified_on = %s
                WHERE risk_register_id = %s;
            """, (valid_user_id, now_dt, reg_id))

            # 4. Insert Audit History into risk_register_hist
            try:
                cur.execute(f"""
                    INSERT INTO {DB_SCHEMA}.risk_register_hist (
                        risk_register_id, risk_id, risk_name, dept_id, risk_owner_id, risk_co_owner_id,
                        financial_year, risk_status, risk_progress,
                        risk_function_head_approval_status, risk_function_head_approval_remark,
                        risk_function_head_approval_on, risk_function_head_approval_by,
                        risk_manager_approval_status, risk_manager_approval_remark,
                        risk_manager_approved_on, risk_manager_approval_by,
                        risk_head_approval_status, risk_head_approval_remark,
                        risk_head_approved_on, risk_head_approval_by,
                        created_by, created_on, modified_by, modified_on, is_active, is_deleted
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s,
                        NULL, %s,
                        NULL, NULL,
                        NULL, NULL,
                        NULL, NULL,
                        NULL, NULL,
                        NULL, NULL,
                        %s, %s, %s, %s, %s, %s
                    );
                """, (
                    reg_id, r_id_code, r_title, risk_row.get("dept_id"), risk_row.get("risk_owner_id"), risk_row.get("risk_co_owner_id"),
                    risk_row.get("financial_year"), 2, risk_row.get("risk_progress"),
                    remark or "Resubmitted for Functional Head review (previous approvals reset)",
                    risk_row.get("created_by"), risk_row.get("created_on") or now_dt,
                    valid_user_id, now_dt, risk_row.get("is_active", 1), 0
                ))
            except Exception as hist_err:
                logger.warning(f"Could not insert risk history on resubmission: {hist_err}")

            conn.commit()
            cur.close()
            conn.close()

            # 5. Non-blocking email trigger if available
            try:
                from ERM_API.app.core.database import SessionLocal
                from ERM_API.app.services.email_event_service import send_function_approval_email_seq
                with SessionLocal() as db_session:
                    send_function_approval_email_seq(db_session, reg_id, 1)
            except Exception as mail_err:
                logger.debug(f"Email notification dispatch skipped or completed: {mail_err}")

            return {
                "success": True,
                "risk_id": r_id_code,
                "risk_register_id": reg_id,
                "risk_title": r_title,
                "action": "Resubmitted",
                "stage": "Stage 1: Functional Head Approval Queue",
                "next_queue": "Stage 1: Functional Head Review",
                "resubmitted_by": user_display_name,
                "resubmitted_role": user_role,
                "timestamp": now_str,
                "remark": remark
            }
        except Exception as e:
            logger.error(f"Error executing resubmit_risk: {e}", exc_info=True)
            if conn:
                try:
                    conn.rollback()
                    conn.close()
                except Exception:
                    pass
            return {"success": False, "message": str(e)}

    def get_user_daily_briefing(
        self,
        user_id: Optional[int] = None,
        role_name: Optional[str] = None,
        dept_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate proactive personalized pending metrics for morning briefing."""
        conn = self._get_connection()
        if not conn:
            return {"pending_count": 0, "items": []}
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            role_lower = str(role_name or "").lower()

            if "function" in role_lower or "_fh" in role_lower:
                query = f"""
                    SELECT risk_register_id, risk_id, risk_name, created_on, financial_year
                    FROM {DB_SCHEMA}.risk_register
                    WHERE is_deleted = 0 AND risk_status = 2 AND (dept_id = %s OR %s IS NULL)
                    ORDER BY risk_register_id DESC LIMIT 5;
                """
                cur.execute(query, (dept_id, dept_id))
                items = cur.fetchall()
                briefing_type = "Pending Functional Head Approvals"
            elif "manager" in role_lower or "_rm" in role_lower:
                query = f"""
                    SELECT risk_register_id, risk_id, risk_name, created_on, financial_year
                    FROM {DB_SCHEMA}.risk_register
                    WHERE is_deleted = 0 AND risk_status = 3
                    ORDER BY risk_register_id DESC LIMIT 5;
                """
                cur.execute(query)
                items = cur.fetchall()
                briefing_type = "Pending Risk Manager Validations"
            elif "head" in role_lower or "_rh" in role_lower:
                query = f"""
                    SELECT risk_register_id, risk_id, risk_name, created_on, financial_year
                    FROM {DB_SCHEMA}.risk_register
                    WHERE is_deleted = 0 AND risk_status = 4
                    ORDER BY risk_register_id DESC LIMIT 5;
                """
                cur.execute(query)
                items = cur.fetchall()
                briefing_type = "Pending Risk Head Final Approvals"
            elif "owner" in role_lower and "action" not in role_lower:
                # Risk Owner: check for returned risks (status 6) or drafts (status 1) first
                query = f"""
                    SELECT 
                        r.risk_register_id, r.risk_id, r.risk_name, 
                        r.created_on, r.financial_year,
                        COALESCE(r.risk_manager_approval_remark, r.risk_function_head_approval_remark, 'Revision / Action Required') as action_plan
                    FROM {DB_SCHEMA}.risk_register r
                    WHERE r.is_deleted = 0 
                      AND (r.risk_status = 6 OR r.risk_status = 1)
                      AND (r.risk_owner_id = %s OR r.created_by = %s OR (r.dept_id = %s AND %s IS NULL) OR %s IS NULL)
                    ORDER BY r.risk_register_id DESC LIMIT 5;
                """
                cur.execute(query, (user_id, user_id, dept_id, user_id, user_id))
                items = cur.fetchall()
                briefing_type = "Risks Pending Revision / Action"
                if not items:
                    query = f"""
                        SELECT t.risk_treatment_id, r.risk_id, r.risk_name, t.action_plan, t.target_date
                        FROM {DB_SCHEMA}.risk_treatment t
                        JOIN {DB_SCHEMA}.risk_register r ON t.risk_register_id = r.risk_register_id
                        WHERE t.is_deleted = 0 AND (t.action_owner_id = %s OR r.risk_owner_id = %s OR %s IS NULL)
                        ORDER BY t.risk_treatment_id DESC LIMIT 5;
                    """
                    cur.execute(query, (user_id, user_id, user_id))
                    items = cur.fetchall()
                    briefing_type = "Assigned Mitigation Action Plans"
            else:
                query = f"""
                    SELECT t.risk_treatment_id, r.risk_id, r.risk_name, t.action_plan, t.target_date
                    FROM {DB_SCHEMA}.risk_treatment t
                    JOIN {DB_SCHEMA}.risk_register r ON t.risk_register_id = r.risk_register_id
                    WHERE t.is_deleted = 0 AND (t.action_owner_id = %s OR %s IS NULL)
                    ORDER BY t.risk_treatment_id DESC LIMIT 5;
                """
                cur.execute(query, (user_id, user_id))
                items = cur.fetchall()
                briefing_type = "Assigned Mitigation Action Plans"

            cur.close()
            conn.close()
            return {
                "briefing_type": briefing_type,
                "pending_count": len(items),
                "items": [dict(r) for r in items]
            }
        except Exception as e:
            logger.error(f"Error generating daily briefing: {e}", exc_info=True)
            if conn:
                conn.close()
            return {"pending_count": 0, "items": []}

    def get_risk_matrix_distribution(self, dept_id: Optional[int] = None) -> Dict[str, Any]:
        """Fetch 5x5 Inherent Risk Matrix distribution (Likelihood vs Impact) and counts."""
        conn = self._get_connection()
        if not conn:
            return {"total": 0, "matrix": {}, "critical": [], "high": [], "medium": [], "low": []}
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            query = f"""
                SELECT 
                    r.risk_id,
                    r.risk_name,
                    COALESCE(rd.inherent_risk_likelihood_id, 2) as likelihood,
                    COALESCE(rd.inherent_risk_impact_id, 2) as impact,
                    COALESCE(d.dept_name, 'Enterprise') as department
                FROM {DB_SCHEMA}.risk_register r
                LEFT JOIN {DB_SCHEMA}.risk_description rd ON r.risk_register_id = rd.risk_register_id
                LEFT JOIN {DB_SCHEMA}.mst_department d ON r.dept_id = d.id
                WHERE r.is_deleted = 0
            """
            params = []
            if dept_id:
                query += " AND r.dept_id = %s"
                params.append(dept_id)

            cur.execute(query, params)
            rows = cur.fetchall()
            cur.close()
            conn.close()

            grid = {f"{l}x{i}": [] for l in range(1, 6) for i in range(1, 6)}
            critical_list, high_list, medium_list, low_list = [], [], [], []

            for r in rows:
                l = max(1, min(5, int(r["likelihood"] or 2)))
                i = max(1, min(5, int(r["impact"] or 2)))
                score = l * i
                item = {"risk_id": r["risk_id"], "risk_name": r["risk_name"], "department": r["department"], "score": score, "coords": f"{l}x{i}"}
                grid[f"{l}x{i}"].append(item)

                if score >= 16:
                    critical_list.append(item)
                elif score >= 10:
                    high_list.append(item)
                elif score >= 5:
                    medium_list.append(item)
                else:
                    low_list.append(item)

            return {
                "total": len(rows),
                "grid": {k: len(v) for k, v in grid.items()},
                "grid_items": grid,
                "critical_count": len(critical_list),
                "high_count": len(high_list),
                "medium_count": len(medium_list),
                "low_count": len(low_list),
                "critical": critical_list,
                "high": high_list,
                "medium": medium_list,
                "low": low_list
            }
        except Exception as e:
            logger.error(f"Error fetching risk matrix distribution: {e}", exc_info=True)
            if conn:
                conn.close()
            return {"total": 0, "matrix": {}, "critical": [], "high": [], "medium": [], "low": []}


erm_db = ERMDatabaseService()
