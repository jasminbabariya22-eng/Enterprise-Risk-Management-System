import os
import sys
sys.path.insert(0, os.path.abspath("d:/ERM"))
import psycopg2
from psycopg2.extras import RealDictCursor
from ERM_Copilot.services.db_service import ERMDatabaseService, DB_SCHEMA

def main():
    db = ERMDatabaseService()
    conn = db._get_connection(readonly=True)
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = %s AND table_type = 'BASE TABLE'
        ORDER BY table_name;
    """, [DB_SCHEMA])
    tables = [r['table_name'] for r in cur.fetchall()]
    print("Tables in schema:", tables)

    cur.execute(f"SELECT * FROM {DB_SCHEMA}.mst_department WHERE (is_deleted = 0 OR is_deleted IS NULL) ORDER BY id;")
    depts = cur.fetchall()
    print("\nDepartments:")
    for d in depts:
        print(f"  {dict(d)}")

    cur.execute(f"SELECT id, log_id, first_name, last_name, user_type_id, dept_id FROM {DB_SCHEMA}.mst_users WHERE (is_deleted = 0 OR is_deleted IS NULL) ORDER BY id;")
    users = cur.fetchall()
    print("\nUsers:")
    for u in users:
        print(f"  ID: {u['id']}, LogID: {u['log_id']}, Name: {u['first_name']} {u['last_name']}, UserType: {u['user_type_id']}, DeptID: {u['dept_id']}")

    cur.execute(f"SELECT id, name FROM {DB_SCHEMA}.mst_user_type ORDER BY id;")
    user_types = cur.fetchall()
    print("\nUser Types:")
    for ut in user_types:
        print(f"  ID: {ut['id']}, Name: {ut['name']}")

    cur.execute(f"SELECT id, status_name FROM {DB_SCHEMA}.mst_status ORDER BY id;")
    statuses = cur.fetchall()
    print("\nStatuses:")
    for s in statuses:
        print(f"  ID: {s['id']}, Name: {s['status_name']}")

    for tbl in ['risk_register', 'risk_description', 'risk_treatment', 'risk_action_followup', 'risk_register_hist', 'risk_description_hist', 'risk_treatment_hist', 'mst_email_job']:
        cur.execute(f"""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_schema = %s AND table_name = %s
            ORDER BY ordinal_position;
        """, [DB_SCHEMA, tbl])
        cols = cur.fetchall()
        print(f"\n--- Columns in {tbl} ---")
        print(", ".join([c['column_name'] for c in cols]))


if __name__ == "__main__":
    main()
