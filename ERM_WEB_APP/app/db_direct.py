import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor

logger = logging.getLogger(__name__)

DB_HOST = os.getenv("POSTGRES_HOST", "localhost")
DB_PORT = int(os.getenv("POSTGRES_PORT", "5433"))
DB_NAME = os.getenv("POSTGRES_DB_ERM", "MassERS")
DB_USER = os.getenv("POSTGRES_USER", "postgres")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "Alethe@123")
DB_SCHEMA = "ers"

def get_db_conn():
    for p in [DB_PORT, 5433, 5432]:
        try:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=p,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASS,
                connect_timeout=3
            )
            return conn
        except Exception:
            continue
    return None

def fetch_all_users():
    conn = get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT u.id, u.log_id, u.first_name, u.last_name, u.email, u.dept_id
            FROM {DB_SCHEMA}.mst_users u
            WHERE u.is_deleted = 0 AND u.status = 'Active'
            ORDER BY u.id ASC;
        """)
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error in fetch_all_users: {e}")
        return []

def fetch_dept_users(dept_id):
    conn = get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT u.id, u.log_id, u.first_name, u.last_name, u.email, u.dept_id
            FROM {DB_SCHEMA}.mst_users u
            WHERE (u.dept_id = %s OR %s IS NULL) AND u.is_deleted = 0 AND u.status = 'Active'
            ORDER BY u.id ASC;
        """, (dept_id, dept_id))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error in fetch_dept_users: {e}")
        return []

def fetch_statuses(status_type="risk"):
    conn = get_db_conn()
    if not conn:
        return []
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        type_str = str(status_type).lower() if status_type else "risk"
        if type_str in ["risk", "approval", "all"]:
            cur.execute(f"""
                SELECT id, status_name, type 
                FROM {DB_SCHEMA}.mst_status 
                WHERE is_deleted = 0 AND UPPER(type) IN ('RISK', 'APPROVAL')
                ORDER BY id ASC;
            """)
        elif type_str in ["action", "action_plan", "treatment"]:
            cur.execute(f"""
                SELECT id, status_name, type 
                FROM {DB_SCHEMA}.mst_status 
                WHERE is_deleted = 0 AND UPPER(type) = 'ACTION'
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
        return [dict(r) for r in rows]
    except Exception as e:
        logger.error(f"Error in fetch_statuses: {e}")
        return []

def fetch_risk_by_id_full(risk_register_id):
    conn = get_db_conn()
    if not conn:
        return None
    try:
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute(f"""
            SELECT rr.risk_register_id, rr.risk_id, rr.dept_id, rr.risk_owner_id, rr.risk_co_owner_id,
                   rr.financial_year, rr.risk_status, rr.risk_name,
                   u_ro.log_id as rd_risk_owner_name,
                   u_co.log_id as rd_risk_co_owner_name,
                   st.status_name as rd_risk_status_name,
                   rr.risk_function_head_approval_status,
                   rr.risk_head_approval_status,
                   rr.risk_manager_approval_status
            FROM {DB_SCHEMA}.risk_register rr
            LEFT JOIN {DB_SCHEMA}.mst_users u_ro ON rr.risk_owner_id = u_ro.id
            LEFT JOIN {DB_SCHEMA}.mst_users u_co ON rr.risk_co_owner_id = u_co.id
            LEFT JOIN {DB_SCHEMA}.mst_status st ON rr.risk_status = st.id
            WHERE rr.risk_register_id = %s AND rr.is_deleted = 0;
        """, (risk_register_id,))
        rr_row = cur.fetchone()
        if not rr_row:
            cur.close()
            conn.close()
            return None
        
        risk_item = dict(rr_row)
        
        cur.execute(f"""
            SELECT rd.risk_description_id, rd.risk_register_id, rd.risk_description,
                   rd.inherent_risk_likelihood_id as inherent_likelihood,
                   rd.inherent_risk_impact_id as inherent_impact,
                   rd.mitigation,
                   rd.current_risk_likelihood_id as current_likelihood,
                   rd.current_risk_impact_id as current_impact
            FROM {DB_SCHEMA}.risk_description rd
            WHERE rd.risk_register_id = %s AND rd.is_deleted = 0;
        """, (risk_register_id,))
        descriptions = cur.fetchall()
        desc_list = []
        for d in descriptions:
            d_dict = dict(d)
            lh = d_dict.get('inherent_likelihood') or 3
            imp = d_dict.get('inherent_impact') or 3
            imp_map = {1: 'A', 2: 'B', 3: 'C', 4: 'D', 5: 'E'}
            d_dict['inherent_risk_level'] = f"{lh}{imp_map.get(imp, 'C')}"
            
            c_lh = d_dict.get('current_likelihood') or 2
            c_imp = d_dict.get('current_impact') or 2
            d_dict['current_risk_level'] = f"{c_lh}{imp_map.get(c_imp, 'B')}"
            
            cur.execute(f"""
                SELECT rt.risk_treatment_id, rt.risk_description_id, rt.risk_register_id,
                       rt.action_plan, rt.action_owner_id, rt.target_date, 
                       rt.action_status_id as status_id,
                       rt.progress as progress_percentage
                FROM {DB_SCHEMA}.risk_treatment rt
                WHERE rt.risk_description_id = %s AND rt.is_deleted = 0;
            """, (d_dict['risk_description_id'],))
            treatments = cur.fetchall()
            d_dict['treatments'] = [dict(t) for t in treatments]
            desc_list.append(d_dict)
        
        risk_item['risk_descriptions'] = desc_list
        cur.close()
        conn.close()
        return risk_item
    except Exception as e:
        logger.error(f"Error in fetch_risk_by_id_full: {e}")
        return None
