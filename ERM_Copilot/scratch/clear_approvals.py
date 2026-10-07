import os
import sys

sys.path.insert(0, os.path.abspath("d:/ERM"))
from psycopg2.extras import RealDictCursor
from ERM_Copilot.services.db_service import ERMDatabaseService, DB_SCHEMA

def reset_all_approvals():
    db = ERMDatabaseService()
    conn = db._get_connection(readonly=False)
    if not conn:
        print("Failed to connect to DB")
        return False

    cur = conn.cursor(cursor_factory=RealDictCursor)
    try:
        print("Resetting all approval actions across all risks...")
        cur.execute(f"""
            UPDATE {DB_SCHEMA}.risk_register
            SET 
                risk_status = 2,
                risk_function_head_approval_status = NULL,
                risk_function_head_approval_remark = NULL,
                risk_function_head_approval_on = NULL,
                risk_function_head_approval_by = NULL,
                risk_manager_approval_status = NULL,
                risk_manager_approval_remark = NULL,
                risk_manager_approved_on = NULL,
                risk_manager_approval_by = NULL,
                risk_head_approval_status = NULL,
                risk_head_approval_remark = NULL,
                risk_head_approved_on = NULL,
                risk_head_approval_by = NULL;
        """)
        
        # Clear any treatment approval flags if present
        cur.execute(f"""
            UPDATE {DB_SCHEMA}.risk_treatment
            SET 
                approved_by = NULL,
                approved_on = NULL,
                approval_remark = NULL,
                approval_status = NULL;
        """)

        # Clean history and audit tables
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_register_hist RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_description_hist RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_treatment_hist RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.risk_action_followup RESTART IDENTITY CASCADE;")
        cur.execute(f"TRUNCATE TABLE {DB_SCHEMA}.mst_email_job RESTART IDENTITY CASCADE;")

        conn.commit()
        print("Successfully cleared all approval actions. All risks are now in Stage 2 (Submitted to Function Head).")
        return True
    except Exception as e:
        conn.rollback()
        print(f"Error resetting approvals: {e}")
        return False
    finally:
        cur.close()
        conn.close()

if __name__ == "__main__":
    reset_all_approvals()
