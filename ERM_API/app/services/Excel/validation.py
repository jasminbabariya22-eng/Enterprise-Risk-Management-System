import re
import logging
from datetime import datetime
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.user import User
from app.models.department import Department
from app.models.risk_register import RiskRegister
from app.models.risk_description import RiskDescription
from app.models.risk_treatment import RiskTreatment

logger = logging.getLogger("risk_import_validation")

EXPECTED_COLUMNS = [
    "Department",
    "S. No",
    "Risk Category",
    "Risk Owner",
    "Risk Co Owner",
    "Inherent Risk Level",
    "Current Mitigation",
    "Current Risk Level",
    "Action Owner",
    "Action Plan",
    "Targeted Date",
    "FH",
    "RM",
    "RH"
]

# Helper to get SQLAlchemy Column maximum length
def get_column_max_length(model, attribute_name: str) -> int:
    column = getattr(model, attribute_name, None)
    if column is not None and hasattr(column, "type") and hasattr(column.type, "length"):
        return column.type.length
    return None

def validate_column_sequence(actual_headers: list[str]) -> tuple[bool, str, list[dict]]:
    expected_normalized = [col.strip().lower() for col in EXPECTED_COLUMNS]
    actual_normalized = [col.strip().lower() for col in actual_headers]

    errors = []
    
    # 1. Missing columns check
    missing = []
    for exp in EXPECTED_COLUMNS:
        exp_clean = exp.strip().lower()
        found = False
        for act in actual_normalized:
            if act.startswith(exp_clean) or exp_clean in act:
                found = True
                break
        if not found:
            missing.append(exp)
            errors.append({
                "row": "Header",
                "column": exp,
                "value": "",
                "message": f"Required column '{exp}' is missing."
            })
            
    if missing:
        msg = f"Required column '{missing[0]}' is missing."
        return False, msg, errors

    # 2. Extra columns check
    extra = []
    for act in actual_headers:
        act_clean = act.strip().lower()
        found = False
        for exp in expected_normalized:
            if act_clean.startswith(exp) or exp in act_clean:
                found = True
                break
        if not found:
            extra.append(act)
            errors.append({
                "row": "Header",
                "column": act,
                "value": act,
                "message": f"Unknown column '{act}'."
            })
            
    if extra:
        msg = f"Unknown column '{extra[0]}'."
        return False, msg, errors

    # 3. Exact column sequence check
    mismatches = []
    for i, exp in enumerate(EXPECTED_COLUMNS):
        if i < len(actual_headers):
            act = actual_headers[i]
            exp_clean = re.sub(r"\s+", " ", exp.lower().strip())
            act_clean = re.sub(r"\s+", " ", act.lower().strip())
            if exp_clean not in act_clean:
                mismatches.append((exp, act))

    if mismatches:
        expected_str = "\n".join([f"{idx+1}. {col}" for idx, col in enumerate(EXPECTED_COLUMNS)])
        found_str = "\n".join([f"{idx+1}. {col}" for idx, col in enumerate(actual_headers)])
        msg = f"Column sequence is invalid.\n\nExpected:\n\n{expected_str}\n\nFound:\n\n{found_str}"
        
        seq_errors = []
        for exp, act in mismatches:
            seq_errors.append({
                "row": "Header",
                "column": exp,
                "value": act,
                "message": f"Expected: {exp}, Found: {act}"
            })
        return False, msg, seq_errors

    return True, "", []

def validate_excel_file(db: Session, excel_path: str) -> dict:
    errors = []

    try:
        with pd.ExcelFile(excel_path) as xl:
            if not xl.sheet_names:
                return {
                    "success": False,
                    "message": "Excel validation failed.",
                    "total_errors": 1,
                    "errors": [{
                        "row": "N/A",
                        "column": "Sheet",
                        "value": "",
                        "message": "Excel sheet does not exist."
                    }]
                }
            # Use first sheet
            sheet_name = xl.sheet_names[0]
            raw_df = xl.parse(sheet_name, header=None)
    except Exception as e:
        logger.error(f"Failed to load Excel file: {e}")
        return {
            "success": False,
            "message": "Excel validation failed.",
            "total_errors": 1,
            "errors": [{
                "row": "N/A",
                "column": "Excel File",
                "value": "",
                "message": f"Failed to read excel file: {str(e)}"
            }]
        }

    if raw_df.shape[0] < 2:
        return {
            "success": False,
            "message": "Excel validation failed.",
            "total_errors": 1,
            "errors": [{
                "row": "Header",
                "column": "Headers",
                "value": "",
                "message": "Template does not contain sufficient header rows."
            }]
        }

    # Merge Row 0 and Row 1 to find headers
    row0 = raw_df.iloc[0].tolist()
    row1 = raw_df.iloc[1].tolist()
    actual_headers = []
    for r0, r1 in zip(row0, row1):
        v0 = str(r0).strip() if pd.notna(r0) else ""
        v1 = str(r1).strip() if pd.notna(r1) else ""
        combined = f"{v0} {v1}".strip()
        actual_headers.append(combined)

    # Clean header whitespaces
    actual_headers = [re.sub(r"\s+", " ", col).strip() for col in actual_headers]

    # Validate Columns
    is_valid_cols, col_msg, col_errors = validate_column_sequence(actual_headers)
    if not is_valid_cols:
        for err in col_errors:
            logger.error(f"ERROR: Row {err['row']} - Column {err['column']}: {err['message']}")
        return {
            "success": False,
            "message": col_msg,
            "total_errors": len(col_errors),
            "errors": col_errors
        }

    # Slice data
    df = raw_df.copy()
    df = df.iloc[:, :len(EXPECTED_COLUMNS)]
    df.columns = EXPECTED_COLUMNS
    data_df = df.iloc[2:]

    # Build DB Caches
    departments = {
        d.dept_short_name.strip().upper(): d
        for d in db.query(Department).filter(Department.is_deleted == 0).all()
    }

    # Query all active users
    users = db.query(User).filter(User.is_deleted == 0).all()
    users_by_logid = {
        u.log_id.strip().lower(): u for u in users if u.log_id
    }
    users_by_email = {
        u.email.strip().lower(): u for u in users if u.email
    }
    users_by_name = {}
    for u in users:
        full_name = f"{u.first_name} {u.last_name}".strip().lower()
        users_by_name[full_name] = u
        if not u.last_name or u.last_name.strip() in ("", "-"):
            users_by_name[u.first_name.strip().lower()] = u

    # Cache existing Risk IDs
    existing_risk_ids = {
        r.risk_id.strip().upper()
        for r in db.query(RiskRegister).filter(RiskRegister.is_deleted == 0).all() if r.risk_id
    }

    # Keep track of duplicates inside the Excel sheet
    seen_risk_ids = {} # risk_id_upper -> list of row numbers
    seen_s_nos = {} # s_no_str -> list of row numbers

    # Model length limits
    risk_name_limit = get_column_max_length(RiskRegister, "risk_name") or 250
    risk_desc_limit = get_column_max_length(RiskDescription, "risk_description")
    mitigation_limit = get_column_max_length(RiskDescription, "mitigation")
    action_plan_limit = get_column_max_length(RiskTreatment, "action_plan")

    # Validation loop
    for index, row in data_df.iterrows():
        row_num = index + 1

        # Check for empty row
        is_empty = True
        for col in EXPECTED_COLUMNS:
            val = row[col]
            if pd.notna(val) and str(val).strip() != "":
                is_empty = False
                break
        if is_empty:
            continue

        # Extract values safely
        dept_val = str(row.get("Department", "")).strip() if pd.notna(row.get("Department")) else ""
        sno_val = str(row.get("S. No", "")).strip() if pd.notna(row.get("S. No")) else ""
        category_val = str(row.get("Risk Category", "")).strip() if pd.notna(row.get("Risk Category")) else ""
        owner_val = str(row.get("Risk Owner", "")).strip() if pd.notna(row.get("Risk Owner")) else ""
        co_owner_val = str(row.get("Risk Co Owner", "")).strip() if pd.notna(row.get("Risk Co Owner")) else ""
        desc_val = category_val  # Risk description maps to Risk Category since there is no separate column
        inherent_val = str(row.get("Inherent Risk Level", "")).strip() if pd.notna(row.get("Inherent Risk Level")) else ""
        mitigation_val = str(row.get("Current Mitigation", "")).strip() if pd.notna(row.get("Current Mitigation")) else ""
        current_val = str(row.get("Current Risk Level", "")).strip() if pd.notna(row.get("Current Risk Level")) else ""
        action_owner_val = str(row.get("Action Owner", "")).strip() if pd.notna(row.get("Action Owner")) else ""
        action_plan_val = str(row.get("Action Plan", "")).strip() if pd.notna(row.get("Action Plan")) else ""
        target_date_val = row.get("Targeted Date")
        fh_val = str(row.get("FH", "")).strip() if pd.notna(row.get("FH")) else ""
        rm_val = str(row.get("RM", "")).strip() if pd.notna(row.get("RM")) else ""
        rh_val = str(row.get("RH", "")).strip() if pd.notna(row.get("RH")) else ""

        # 1. Validate Mandatory Fields
        if not dept_val:
            errors.append({"row": row_num, "column": "Department", "value": "", "message": "Department cannot be empty."})
        if not sno_val:
            errors.append({"row": row_num, "column": "S. No", "value": "", "message": "S. No cannot be empty."})
        if not category_val:
            errors.append({"row": row_num, "column": "Risk Category", "value": "", "message": "Risk Category cannot be empty."})
        if not owner_val:
            errors.append({"row": row_num, "column": "Risk Owner", "value": "", "message": "Risk Owner cannot be empty."})
        if not desc_val:
            errors.append({"row": row_num, "column": "Risk Description", "value": "", "message": "Risk Description cannot be empty."})
        if not inherent_val:
            errors.append({"row": row_num, "column": "Inherent Risk Level", "value": "", "message": "Inherent Risk Level cannot be empty."})
        if not current_val:
            errors.append({"row": row_num, "column": "Current Risk Level", "value": "", "message": "Current Risk Level cannot be empty."})

        # 2. Datatype Validation
        # S. No must be integer
        s_no_is_int = True
        if sno_val:
            try:
                # pandas float to int conversion check
                float_val = float(sno_val)
                if not float_val.is_integer():
                    raise ValueError()
            except ValueError:
                errors.append({
                    "row": row_num,
                    "column": "S. No",
                    "value": sno_val,
                    "message": f"S. No must be integer. Found '{sno_val}'."
                })
                s_no_is_int = False

        # Targeted Date must be valid date
        if pd.notna(target_date_val) and str(target_date_val).strip() != "":
            if not isinstance(target_date_val, (datetime, pd.Timestamp)):
                try:
                    pd.to_datetime(target_date_val)
                except Exception:
                    errors.append({
                        "row": row_num,
                        "column": "Targeted Date",
                        "value": str(target_date_val),
                        "message": f"Targeted Date must be date. Found '{target_date_val}'."
                    })

        # 3. Maximum Length Validation
        if category_val and len(category_val) > risk_name_limit:
            errors.append({
                "row": row_num,
                "column": "Risk Category",
                "value": category_val,
                "message": f"Risk Category exceeds maximum length.\n\nMaximum : {risk_name_limit}\n\nFound : {len(category_val)}"
            })
        if desc_val and risk_desc_limit and len(desc_val) > risk_desc_limit:
            errors.append({
                "row": row_num,
                "column": "Risk Description",
                "value": desc_val,
                "message": f"Risk Description exceeds maximum length.\n\nMaximum : {risk_desc_limit}\n\nFound : {len(desc_val)}"
            })
        if mitigation_val and mitigation_limit and len(mitigation_val) > mitigation_limit:
            errors.append({
                "row": row_num,
                "column": "Current Mitigation",
                "value": mitigation_val,
                "message": f"Current Mitigation exceeds maximum length.\n\nMaximum : {mitigation_limit}\n\nFound : {len(mitigation_val)}"
            })
        if action_plan_val and action_plan_limit and len(action_plan_val) > action_plan_limit:
            errors.append({
                "row": row_num,
                "column": "Action Plan",
                "value": action_plan_val,
                "message": f"Action Plan exceeds maximum length.\n\nMaximum : {action_plan_limit}\n\nFound : {len(action_plan_val)}"
            })

        # 4. Department validation
        dept_obj = None
        if dept_val:
            dept_key = dept_val.upper()
            if dept_key not in departments:
                errors.append({
                    "row": row_num,
                    "column": "Department",
                    "value": dept_val,
                    "message": f"Department '{dept_val}' does not exist."
                })
            else:
                dept_obj = departments[dept_key]

        # User helper lookup
        def lookup_user(user_str: str) -> tuple[bool, User]:
            if not user_str:
                return False, None
            clean_user = user_str.strip().lower()
            u = users_by_logid.get(clean_user)
            if u is None:
                u = users_by_email.get(clean_user)
            if u is None:
                u = users_by_name.get(clean_user)
            return u is not None, u

        # 5. Risk Owner validation (must exist and department must match)
        if owner_val:
            exists, user_obj = lookup_user(owner_val)
            if not exists:
                errors.append({
                    "row": row_num,
                    "column": "Risk Owner",
                    "value": owner_val,
                    "message": f"Risk Owner '{owner_val}' does not exist."
                })
            else:
                # Verify department matches
                if dept_obj and user_obj.dept_id != dept_obj.id:
                    errors.append({
                        "row": row_num,
                        "column": "Risk Owner",
                        "value": owner_val,
                        "message": f"Risk Owner '{owner_val}' does not exist in department '{dept_val}'."
                    })

        # 6. Co Owner validation (must exist)
        if co_owner_val:
            exists, user_obj = lookup_user(co_owner_val)
            if not exists:
                errors.append({
                    "row": row_num,
                    "column": "Risk Co Owner",
                    "value": co_owner_val,
                    "message": f"Co Owner '{co_owner_val}' does not exist."
                })

        # 7. Action Owner validation (must exist)
        if action_owner_val:
            exists, _ = lookup_user(action_owner_val)
            if not exists:
                errors.append({
                    "row": row_num,
                    "column": "Action Owner",
                    "value": action_owner_val,
                    "message": f"Action Owner '{action_owner_val}' does not exist."
                })

        # FH, RM, RH validation (must exist if provided)
        if fh_val:
            exists, _ = lookup_user(fh_val)
            if not exists:
                errors.append({
                    "row": row_num,
                    "column": "FH",
                    "value": fh_val,
                    "message": f"Functional Head '{fh_val}' does not exist."
                })
        if rm_val:
            exists, _ = lookup_user(rm_val)
            if not exists:
                errors.append({
                    "row": row_num,
                    "column": "RM",
                    "value": rm_val,
                    "message": f"Risk Manager '{rm_val}' does not exist."
                })
        if rh_val:
            exists, _ = lookup_user(rh_val)
            if not exists:
                errors.append({
                    "row": row_num,
                    "column": "RH",
                    "value": rh_val,
                    "message": f"Risk Head '{rh_val}' does not exist."
                })

        # 8. Risk Level Format check
        RISK_CODE_RE = re.compile(r"^([1-5])\s*[-]?\s*([A-Ea-e])$")
        if inherent_val:
            clean_inh = inherent_val.replace(" ", "")
            if not RISK_CODE_RE.match(clean_inh):
                errors.append({
                    "row": row_num,
                    "column": "Inherent Risk Level",
                    "value": inherent_val,
                    "message": "Invalid Inherent Risk Level."
                })
        if current_val:
            clean_cur = current_val.replace(" ", "")
            if not RISK_CODE_RE.match(clean_cur):
                errors.append({
                    "row": row_num,
                    "column": "Current Risk Level",
                    "value": current_val,
                    "message": "Invalid Current Risk Level."
                })

        # 9. Duplicate S. No / Risk ID checking inside Excel
        if s_no_is_int and sno_val:
            s_no_key = str(int(float(sno_val)))
            if s_no_key in seen_s_nos:
                seen_s_nos[s_no_key].append(row_num)
            else:
                seen_s_nos[s_no_key] = [row_num]

        # 10. Database check if Risk ID already exists (using S. No or generated ID)
        # if dept_obj and s_no_is_int and sno_val:
        #     s_no_int = int(float(sno_val))
        #     # Generate risk ID format based on department and S. No
        #     generated_risk_id = f"{dept_obj.dept_short_name.strip().upper()}-{str(s_no_int).zfill(4)}"
            
        #     # Excel duplicate checking for generated ID
        #     if generated_risk_id in seen_risk_ids:
        #         seen_risk_ids[generated_risk_id].append(row_num)
        #     else:
        #         seen_risk_ids[generated_risk_id] = [row_num]
                
        #     # Database check
        #     if generated_risk_id in existing_risk_ids:
        #         errors.append({
        #             "row": row_num,
        #             "column": "S. No",
        #             "value": sno_val,
        #             "message": f"Risk ID '{generated_risk_id}' already exists."
        #         })

    # Add duplicate inside Excel errors
    for risk_id, rows in seen_risk_ids.items():
        if len(rows) > 1:
            rows_str = "\n\n".join([str(r) for r in rows])
            for r in rows:
                errors.append({
                    "row": r,
                    "column": "S. No",
                    "value": risk_id,
                    "message": f"Duplicate Risk ID '{risk_id}' found in Excel.\n\nRows:\n\n{rows_str}"
                })

    # Log validation failures
    for err in errors:
        logger.error(f"ERROR: Row {err['row']} - Column {err['column']}: {err['message']}")

    if errors:
        return {
            "success": False,
            "message": "Excel validation failed.",
            "total_errors": len(errors),
            "errors": errors
        }

    return {
        "success": True,
        "message": "Excel validated successfully."
    }
