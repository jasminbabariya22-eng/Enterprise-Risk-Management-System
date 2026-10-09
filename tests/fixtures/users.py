"""
User fixtures covering all 7 ERM Roles and Departments.
"""
from typing import Dict, Any, List

TEST_USERS: Dict[str, Dict[str, Any]] = {
    "risk_owner": {
        "user_id": "101",
        "log_id": "ro_karan",
        "full_name": "Karan Malhotra",
        "role_name": "Risk Owner",
        "role_id": 4,
        "dept_id": 2,
        "dept_name": "Gas Processing Facilities",
        "email": "karan.malhotra@mass-erm.local"
    },
    "functional_head": {
        "user_id": "201",
        "log_id": "fh_rajesh",
        "full_name": "Rajesh Sharma",
        "role_name": "Functional Head",
        "role_id": 2,
        "dept_id": 2,
        "dept_name": "Gas Processing Facilities",
        "email": "rajesh.sharma@mass-erm.local"
    },
    "risk_manager": {
        "user_id": "301",
        "log_id": "rm_priya",
        "full_name": "Priya Patel",
        "role_name": "Risk Manager",
        "role_id": 3,
        "dept_id": 2,
        "dept_name": "Gas Processing Facilities",
        "email": "priya.patel@mass-erm.local"
    },
    "risk_head": {
        "user_id": "401",
        "log_id": "rh_amit",
        "full_name": "Amitabh Roy",
        "role_name": "Risk Head",
        "role_id": 5,
        "dept_id": 2,
        "dept_name": "Gas Processing Facilities",
        "email": "amitabh.roy@mass-erm.local"
    },
    "auditor": {
        "user_id": "501",
        "log_id": "aud_neha",
        "full_name": "Neha Gupta",
        "role_name": "Auditor",
        "role_id": 6,
        "dept_id": 1,
        "dept_name": "Internal Audit",
        "email": "neha.gupta@mass-erm.local"
    },
    "executive_ceo": {
        "user_id": "601",
        "log_id": "ceo_vikram",
        "full_name": "Vikram Singhania",
        "role_name": "Executive / CEO",
        "role_id": 7,
        "dept_id": 1,
        "dept_name": "Executive Management",
        "email": "vikram.singhania@mass-erm.local"
    },
    "super_admin": {
        "user_id": "1",
        "log_id": "admin",
        "full_name": "System Administrator",
        "role_name": "Super Admin",
        "role_id": 1,
        "dept_id": 1,
        "dept_name": "Corporate Governance",
        "email": "admin@mass-erm.local"
    }
}
