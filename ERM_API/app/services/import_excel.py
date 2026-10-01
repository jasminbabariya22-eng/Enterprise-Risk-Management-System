import sys
import os

ROOT_DIR = os.path.abspath(
    os.path.join(
        os.path.dirname(__file__),
        "..",
        ".."
    )
)

sys.path.insert(0, ROOT_DIR)


import pandas as pd
import re
from datetime import datetime
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from app.models.risk_register import RiskRegister
from app.models.risk_description import RiskDescription
from app.models.risk_treatment import RiskTreatment
from app.models.user import User
from app.models.department import Department

# =====================================================
# CONFIGURATION
# =====================================================

DATABASE_URL = (
    "postgresql+psycopg2://postgres:Alethe%40123"
    "@192.168.1.171:5432/MassERS"
)

EXCEL_FILE = r"D:\ESM\Data\1. HR- Risk Register Review_2025_Final.xlsx"

DEFAULT_DEPT_ID = 20
DEFAULT_ROLE_ID = 26
DEFAULT_USER_TYPE_ID = 7
DEFAULT_STATUS = "9"

DEFAULT_CREATED_BY = 1
DEFAULT_PASSWORD = "demo123"

FINANCIAL_YEAR = "2025-26"

DRY_RUN = False

# =====================================================
# DB
# =====================================================

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False
)

# =====================================================
# HELPERS
# =====================================================

impact_map = {
    "A": 1,
    "B": 2,
    "C": 3,
    "D": 4,
    "E": 5
}


def parse_risk_code(code):

    if pd.isna(code):
        return None, None

    code = str(code).strip().upper()

    match = re.match(r"([1-5])([A-E])", code)

    if not match:
        return None, None

    likelihood = int(match.group(1))
    impact = impact_map[match.group(2)]

    return likelihood, impact


def clean_text(value):

    if pd.isna(value):
        return ""

    return str(value).strip()


# =====================================================
# USER CREATION
# =====================================================

def get_or_create_user(db, full_name):

    full_name = clean_text(full_name)

    if not full_name:
        return 1

    existing = (
        db.query(User)
        .filter(
            func.lower(
                func.concat(
                    User.first_name,
                    ' ',
                    User.last_name
                )
            ) == full_name.lower()
        )
        .first()
    )

    if existing:
        return existing.id

    parts = full_name.split()

    first_name = parts[0]

    last_name = (
        " ".join(parts[1:])
        if len(parts) > 1
        else "-"
    )

    log_id = (
        full_name.lower()
        .replace(" ", "_")
        .replace(".", "")
    )

    email = f"{log_id}@ers.local"

    new_user = User(
        log_id=log_id,
        password=DEFAULT_PASSWORD,

        first_name=first_name,
        last_name=last_name,

        email=email,

        dept_id=DEFAULT_DEPT_ID,
        role_id=DEFAULT_ROLE_ID,
        user_type_id=DEFAULT_USER_TYPE_ID,

        status=DEFAULT_STATUS,

        created_by=DEFAULT_CREATED_BY,
        created_on=datetime.utcnow(),

        is_deleted=0
    )

    db.add(new_user)
    db.flush()

    return new_user.id


# =====================================================
# RISK ID GENERATION
# =====================================================

def generate_risk_id(db, dept_id):

    dept = (
        db.query(Department)
        .filter(
            Department.id == dept_id
        )
        .with_for_update()
        .first()
    )

    if not dept:
        raise Exception(
            f"Department not found: {dept_id}"
        )

    dept.last_risk_number += 1

    risk_number = dept.last_risk_number

    risk_id = (
        f"{dept.dept_short_name}-"
        f"{str(risk_number).zfill(4)}"
    )

    return risk_id


# =====================================================
# DUPLICATE CHECK
# =====================================================

def risk_exists(db, description):

    return (
        db.query(RiskDescription)
        .filter(
            func.lower(
                RiskDescription.risk_description
            ) == description.lower()
        )
        .first()
        is not None
    )


# =====================================================
# IMPORT
# =====================================================

def import_excel():

    db = SessionLocal()

    logs = []

    success = 0
    failed = 0
    skipped = 0

    try:

        df = pd.read_excel(EXCEL_FILE)
        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
            .str.replace("\n", " ", regex=False)
            .str.replace(r"\s+", " ", regex=True)
        )

        print(df.columns.tolist())
        

        for index, row in df.iterrows():

            try:

                category = clean_text(
                    row["Category"]
                )

                description = clean_text(
                    row["Risk Description"]
                )

                if not description:
                    continue

                if risk_exists(
                    db,
                    description
                ):
                    skipped += 1

                    logs.append({
                        "Row": index + 1,
                        "Status": "SKIPPED",
                        "Message": "Duplicate Risk"
                    })

                    continue

                owner_name = clean_text(
                    row["Risk Owner"]
                )

                owner_id = get_or_create_user(
                    db,
                    owner_name
                )

                risk_id = generate_risk_id(
                    db,
                    DEFAULT_DEPT_ID
                )

                risk_register = RiskRegister(
                    risk_id=risk_id,
                    risk_name=category,

                    dept_id=DEFAULT_DEPT_ID,
                    risk_owner_id=owner_id,

                    financial_year=FINANCIAL_YEAR,

                    risk_status=9,

                    created_by=DEFAULT_CREATED_BY,
                    created_on=datetime.utcnow(),

                    is_active=1,
                    is_deleted=0
                )

                db.add(risk_register)
                db.flush()

                inherent_likelihood, inherent_impact = (
                    parse_risk_code(
                        row[
                            "Inherent Risk Level"
                        ]
                    )
                )

                current_likelihood, current_impact = (
                    parse_risk_code(
                        row[
                            "Current Risk Level"
                        ]
                    )
                )

                risk_desc = RiskDescription(
                    risk_register_id=
                    risk_register.risk_register_id,

                    risk_id=risk_id,

                    risk_description=description,

                    inherent_risk_likelihood_id=
                    inherent_likelihood,

                    inherent_risk_impact_id=
                    inherent_impact,

                    mitigation=clean_text(
                        row[
                            "Current Mitigation"
                        ]
                    ),

                    current_risk_likelihood_id=
                    current_likelihood,

                    current_risk_impact_id=
                    current_impact,

                    created_by=
                    DEFAULT_CREATED_BY,

                    created_on=
                    datetime.utcnow(),

                    is_deleted=0
                )

                db.add(risk_desc)
                db.flush()

                action_plan = clean_text(
                    row.get("Action Plan", "")
                )

                if action_plan:

                    action_owner = clean_text(
                        row.get(
                            "Action owner",
                            owner_name
                        )
                    )

                    action_owner_id = (
                        get_or_create_user(
                            db,
                            action_owner
                        )
                    )

                    due_date = row.get(
                        "Due Date"
                    )

                    treatment = RiskTreatment(
                        risk_description_id=
                        risk_desc.risk_description_id,

                        risk_register_id=
                        risk_register.risk_register_id,

                        risk_id=risk_id,

                        action_plan=action_plan,

                        action_owner_id=
                        action_owner_id,

                        target_date=
                        due_date,

                        progress="0",

                        created_by=
                        DEFAULT_CREATED_BY,

                        created_on=
                        datetime.utcnow(),

                        is_deleted=0
                    )

                    db.add(treatment)

                if not DRY_RUN:
                    db.commit()
                else:
                    db.rollback()

                success += 1

                logs.append({
                    "Row": index + 1,
                    "Status": "SUCCESS",
                    "Message": risk_id
                })

            except Exception as e:

                db.rollback()

                failed += 1

                logs.append({
                    "Row": index + 1,
                    "Status": "FAILED",
                    "Message": str(e)
                })

        pd.DataFrame(logs).to_excel(
            "import_log.xlsx",
            index=False
        )

        print("=" * 50)
        print("IMPORT COMPLETE")
        print("=" * 50)

        print(f"Imported : {success}")
        print(f"Skipped  : {skipped}")
        print(f"Failed   : {failed}")

        print(
            "Log File : import_log.xlsx"
        )

    finally:
        db.close()


if __name__ == "__main__":
    import_excel()