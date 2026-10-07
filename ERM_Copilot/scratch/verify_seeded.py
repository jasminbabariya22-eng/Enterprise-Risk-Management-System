import os
import sys

sys.path.insert(0, os.path.abspath("d:/ERM"))
from ERM_Copilot.services.db_service import ERMDatabaseService

def verify():
    db = ERMDatabaseService()
    print("--- PENDING FH (Stage 2) ---")
    for r in db.get_pending_approvals(stage="fh"):
        print(f"  {r['risk_id']} | {r['department_name']} | {r['risk_title']}")
    print("\n--- PENDING RM (Stage 3) ---")
    for r in db.get_pending_approvals(stage="rm"):
        print(f"  {r['risk_id']} | {r['department_name']} | {r['risk_title']}")
    print("\n--- PENDING RH (Stage 4) ---")
    for r in db.get_pending_approvals(stage="rh"):
        print(f"  {r['risk_id']} | {r['department_name']} | {r['risk_title']}")

if __name__ == "__main__":
    verify()
