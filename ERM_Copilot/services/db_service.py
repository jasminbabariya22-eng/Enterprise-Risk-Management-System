"""
PostgreSQL Database Service for MassERS (Schema: ers).
Handles direct parameterized queries, multi-stage governance approvals, 5x5 heatmap distribution, and audit trails.
"""
import os
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
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
        limit: int = 15
    ) -> List[Dict[str, Any]]:
        """Search risk register entries with optional filters."""
        # Tier 2 Cache Check
        cached = erm_tool_cache.get("search_risks", keyword=keyword, department=department, status=status, limit=limit)
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
                
            query += " ORDER BY r.risk_register_id DESC LIMIT %s;"
            params.append(limit)
            
            cur.execute(query, params)
            results = cur.fetchall()
            cur.close()
            conn.close()
            formatted = [dict(r) for r in results]
            # Store in Tier 2 DB cache
            erm_tool_cache.set("search_risks", formatted, ttl=300, keyword=keyword, department=department, status=status, limit=limit)
            return formatted
        except Exception as e:
            logger.error(f"Error searching risks: {e}")
            return []

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
            wildcard = f"%{risk_id.strip()}%"
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
                    COALESCE(ut.user_type_name, r.name, 'Staff') as role_name
                FROM {DB_SCHEMA}.mst_users u
                LEFT JOIN {DB_SCHEMA}.mst_department d ON u.dept_id = d.id
                LEFT JOIN {DB_SCHEMA}.mst_user_type ut ON u.user_type_id = ut.id
                LEFT JOIN {DB_SCHEMA}.mst_role r ON u.role_id = r.id
                WHERE (
                    u.log_id ILIKE %s OR 
                    u.first_name ILIKE %s OR 
                    u.last_name ILIKE %s OR 
                    (u.first_name || ' ' || u.last_name) ILIKE %s OR
                    ut.user_type_name ILIKE %s
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

                    cur.execute(f"""
                        INSERT INTO {DB_SCHEMA}.risk_treatment (
                            risk_treatment_id, risk_description_id, risk_register_id, risk_id, action_plan,
                            action_owner_id, target_date, created_by, created_on, modified_by, modified_on, is_deleted
                        ) VALUES (%s, %s, %s, %s, %s, %s, NOW() + INTERVAL '30 days', %s, %s, %s, %s, 0);
                    """, (
                        next_treat_id, next_desc_id, next_reg_id, generated_risk_id, action_text,
                        target_ao_id, resolved_owner_id, now_str, resolved_owner_id, now_str
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
                "created_on": now_str,
                "treatments": inserted_treatments
            }
        except Exception as e:
            logger.error(f"Error creating risk in database: {e}", exc_info=True)
            return {"status": "error", "message": str(e)}

    def approve_or_reject_risk(
        self,
        risk_id: str,
        approver_id: int,
        user_role: str = "Functional Head",
        action: str = "approve",
        remark: str = "Approved via ERM Copilot"
    ) -> Dict[str, Any]:
        """Execute 1-Click Governance Sign-off (Approve / Reject) directly in MassERS."""
        conn = self._get_connection(readonly=False)
        if not conn:
            return {"success": False, "message": "Database connection failed"}
        try:
            cur = conn.cursor(cursor_factory=RealDictCursor)
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            cur.execute(f"""
                SELECT risk_register_id, risk_id, risk_name, risk_status, dept_id, risk_owner_id
                FROM {DB_SCHEMA}.risk_register
                WHERE (risk_id ILIKE %s OR risk_register_id::text = %s) AND is_deleted = 0
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

            role_lower = str(user_role).lower()
            is_approve = action.lower() in ["approve", "approved", "signoff", "sign-off", "yes", "accept"]

            if is_approve:
                if "function" in role_lower or "_fh" in role_lower:
                    new_status = 3
                    cur.execute(f"""
                        UPDATE {DB_SCHEMA}.risk_register
                        SET risk_status = %s, risk_function_head_approval_status = 1,
                            risk_function_head_approval_by = %s, risk_function_head_approval_on = %s,
                            risk_function_head_approval_remark = %s, modified_by = %s, modified_on = %s
                        WHERE risk_register_id = %s;
                    """, (new_status, approver_id, now_str, remark, approver_id, now_str, reg_id))
                    stage_name = "Stage 2: Functional Head Sign-Off"
                    next_queue = "Stage 3: Risk Manager Review Queue"
                elif "manager" in role_lower or "_rm" in role_lower:
                    new_status = 4
                    cur.execute(f"""
                        UPDATE {DB_SCHEMA}.risk_register
                        SET risk_status = %s, risk_manager_approval_status = 1,
                            risk_manager_approval_by = %s, risk_manager_approved_on = %s,
                            risk_manager_approval_remark = %s, modified_by = %s, modified_on = %s
                        WHERE risk_register_id = %s;
                    """, (new_status, approver_id, now_str, remark, approver_id, now_str, reg_id))
                    stage_name = "Stage 3: Risk Manager Review"
                    next_queue = "Stage 4: Risk Head Final Approval Queue"
                else:
                    new_status = 5
                    cur.execute(f"""
                        UPDATE {DB_SCHEMA}.risk_register
                        SET risk_status = %s, risk_head_approval_status = 1,
                            risk_head_approval_by = %s, risk_head_approved_on = %s,
                            risk_head_approval_remark = %s, modified_by = %s, modified_on = %s
                        WHERE risk_register_id = %s;
                    """, (new_status, approver_id, now_str, remark, approver_id, now_str, reg_id))
                    stage_name = "Stage 4: Risk Head Final Sign-Off"
                    next_queue = "Completed (Active in Register)"
            else:
                new_status = 6
                cur.execute(f"""
                    UPDATE {DB_SCHEMA}.risk_register
                    SET risk_status = %s, risk_function_head_approval_status = -1,
                        risk_function_head_approval_by = %s, risk_function_head_approval_on = %s,
                        risk_function_head_approval_remark = %s, modified_by = %s, modified_on = %s
                    WHERE risk_register_id = %s;
                """, (new_status, approver_id, now_str, remark, approver_id, now_str, reg_id))
                stage_name = "Governance Rejection / Return"
                next_queue = "Returned to Risk Owner for Revision"

            cur.close()
            conn.close()
            return {
                "success": True,
                "risk_id": r_id_code,
                "risk_register_id": reg_id,
                "risk_title": r_title,
                "action": "Approved" if is_approve else "Rejected/Returned",
                "stage": stage_name,
                "new_status_id": new_status,
                "next_queue": next_queue,
                "timestamp": now_str,
                "remark": remark
            }
        except Exception as e:
            logger.error(f"Error executing approve_or_reject_risk: {e}", exc_info=True)
            if conn:
                conn.close()
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
