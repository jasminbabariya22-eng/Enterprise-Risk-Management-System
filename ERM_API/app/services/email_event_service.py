from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime
from app.core.config import settings

from app.core.email_templates import build_email_template

from app.models.email_job_mst import EmailJobMst
from app.models.risk_register import RiskRegister
from app.models.risk_treatment import RiskTreatment

from app.models.user import User
from app.core.security import encrypt_text

SCHEMA = settings.DB_SCHEMA    # fetch schema from config for dynamic queries


def get_deptname_by_id(db, dept_id):   
    #dept_id = list(set([uid for uid in dept_id if uid]))
    result = db.execute(
        text(f"""
            SELECT dept_name
            FROM {SCHEMA}.mst_department
            WHERE id = ANY(:ids)
            AND is_deleted = 0
            """),
            {"ids": dept_id}
    ).fetchall()

    #dept_name = [r.dept_name for r in result if r.dept_name]
    dept_name = ''
    if result:
        dept_name = result[0].dept_name
    
    return dept_name

# UTILITY FUNCTIONS 
def get_emails_by_user_ids(db, user_ids):   
    #user_ids = list(set([uid for uid in user_ids if uid]))

    # if not user_ids:
    #     print("No user IDs")
    #     return []

    result = db.execute(
        text(f"""
            SELECT id,email,first_name, last_name
            FROM {SCHEMA}.mst_users
            WHERE id = ANY(:ids)
            AND is_deleted = 0
            """),
            {"ids": user_ids}
    ).fetchall()

    #emails = [r.email for r in result if r.email]
    users = {
            "id": result[0].id,
            "first_name": result[0].first_name,
            "last_name":result[0].last_name,
            "email": result[0].email
        }
        
    #print("Emails fetched:", emails)

    return users


# def get_department_head(db, dept_id):
#     result = db.execute(text("""
#         SELECT head_id
#         FROM mst_department
#         WHERE id = :id
#     """), {"id": dept_id}).fetchone()

#     return result.head_id if result else None


# ROLE BASED (BY NAME FROM DB)
def get_users_by_role_name(db, role_name):
    result = db.execute(text(f"""
        SELECT u.email
        FROM {SCHEMA}.mst_users u
        JOIN {SCHEMA}.mst_user_type r ON r.id = u.user_type_id
        WHERE r.name = :role_name
        AND u.is_deleted = 0
        AND r.is_deleted = 0
    """), {"role_name": role_name}).fetchall()

    return [r.email for r in result if r.email]

def get_users_by_role_name_fd(db, role_name,dept_id):
    result = db.execute(text(f"""
        SELECT u.email
        FROM {SCHEMA}.mst_users u
        JOIN {SCHEMA}.mst_user_type r ON r.id = u.user_type_id
        WHERE r.name = :role_name
        AND u.is_deleted = 0
        AND r.is_deleted = 0
        AND u.dept_id = :dept_id
    """), {"role_name": role_name,"dept_id": dept_id}).fetchall()

    return [r.email for r in result if r.email]



# FUNCTION FOR COMMAN EMAIL BODY BUILDING
def build_risk_details_html(risk,function_name,owner_name,action_message,remark=None):

    remark_html = ""

    if remark:
        remark_html = f"""
        <tr>
            <td><b>Remark</b></td>
            <td>{remark}</td>
        </tr>
        """

    return f"""
    <p>Dear User,</p>

    <p>{action_message}</p>

    <table border="1"
           cellpadding="8"
           cellspacing="0"
           style="border-collapse: collapse;">

        <tr>
            <td><b>Risk ID</b></td>
            <td>{risk.risk_id}</td>
        </tr>

        <tr>
            <td><b>Functional Risk</b></td>
            <td>{function_name}</td>
        </tr>

        <tr>
            <td><b>Risk Owner</b></td>
            <td>{owner_name}</td>
        </tr>

        <tr>
            <td><b>Risk Title</b></td>
            <td>{risk.risk_name}</td>
        </tr>

        <tr>
            <td><b>Financial Year</b></td>
            <td>{risk.financial_year}</td>
        </tr>

        {remark_html}

    </table>

    <p>
        Please review the risk and initiate the required action.
    </p>

    <p>
        Regards,<br>
        Enterprise Risk Management System
    </p>
    """
    

# COMMON EMAIL CONTEXT
def get_risk_email_context(db, risk):

    function_name = get_deptname_by_id(db,[risk.dept_id])
    owner_data = get_emails_by_user_ids(db,[risk.risk_owner_id])
    owner_email = [owner_data["email"]]

    owner_name = (
        f"{owner_data.get('first_name') or ''} "
        f"{owner_data.get('last_name') or ''}"
    ).strip()

    fh = get_users_by_role_name_fd(db,"Functional Head",risk.dept_id)
    rm = get_users_by_role_name(db,"Risk Manager")
    rh = get_users_by_role_name(db,"Risk Head")

    return {
        "function_name": function_name,
        "owner_data": owner_data,
        "owner_email": owner_email,
        "owner_name": owner_name,
        "fh": fh,
        "rm": rm,
        "rh": rh
    }


# EMAIL JOB CREATION
def create_email_job(db, to_list, cc_list, subject, body, created_by=1):
    
    if not to_list:
        print("No TO emails found. Skipping email job.")
        return

    job = EmailJobMst(
        email_server_id=1,
        email_to=",".join(set(to_list)),
        email_cc=",".join(set(cc_list)),
        email_subject=subject,
        email_type = "HTML",
        email_body=body,
        send_status="New",
        next_attempt_at=datetime.now(),
        created_on=datetime.now(),
        created_by = created_by,   # Assuming the email is triggered by the risk owner. Adjust as needed.
        is_deleted=0
    )

    db.add(job)
    # db.commit()
    
    print("Email job inserted")
    
    
##------------------------------Risk Rejection Function-------------------
def send_risk_rejection_email(                      #(TO:-RO, CC:- FH,RM,RH)
                                db,
                                risk_register_id: int,
                                rejected_by_role: str,
                                remark: str = None
                            ):
    
    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_register_id == risk_register_id,
        RiskRegister.is_deleted == 0
    ).first()

    if not risk:
        return

    ctx = get_risk_email_context(db, risk)

    function_list = ctx["function_name"]
    owner = ctx["owner_email"]
    full_name = ctx["owner_name"]

    fh = ctx["fh"]
    rm = ctx["rm"]
    rh = ctx["rh"]

    role_cc_map = {
        "Functional Head": fh + rm,
        "Risk Manager": fh + rm,
        "Risk Head": fh + rm + rh
    }

    cc_emails = list(
        set(role_cc_map.get(
            rejected_by_role,
            fh + rm + rh
        )) - set(owner)
    )

    subject = (
        f"Risk Rejected by {rejected_by_role}"
        f" - {risk.risk_id}"
    )

    content = f"""
    <p>Dear Risk Owner,</p>

    <p>
        The following risk has been
        <b>Rejected</b> by
        <b>{rejected_by_role}</b>.
    </p>

    <table border="1" cellpadding="8" cellspacing="0"
        style="border-collapse: collapse;">
        <tr><td><b>Risk ID</b></td><td>{risk.risk_id}</td></tr>
        <tr><td><b>Functional Risk</b></td><td>{function_list}</td></tr>
        <tr><td><b>Risk Owner</b></td><td>{full_name}</td></tr>
        <tr><td><b>Risk Title</b></td><td>{risk.risk_name}</td></tr>
        <tr><td><b>Financial Year</b></td><td>{risk.financial_year}</td></tr>
        <tr><td><b>Remarks</b></td><td>{remark or '-'}</td></tr>
    </table>

    <p>
        Please review the comments and
        resubmit the risk after necessary changes.
    </p>

    <p>
        Regards,<br>
        Enterprise Risk Management System
    </p>
    """

    body = build_email_template(f"Risk Rejected by {rejected_by_role}",content)

    create_email_job(db,owner,cc_emails,subject,body,created_by=risk.risk_owner_id)


# EVENT 1: RISK CREATED (TO:FH && CC:RO,RM)

def send_risk_created_email(db: Session, risk_register_id: int):

    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_register_id == risk_register_id,
        RiskRegister.is_deleted == 0
    ).first()

    if not risk:
        return

    ctx = get_risk_email_context(db, risk)

    function_list = ctx["function_name"]
    owner = ctx["owner_email"]
    full_name = ctx["owner_name"]

    fh = ctx["fh"]
    rm = ctx["rm"]
    # rh = ctx["rh"]

    cc_emails = list(set(owner + rm) - set(fh))

    subject = f"New Risk Registered - {risk.risk_id}"

    content = build_risk_details_html(
                        risk=risk,
                        function_name=function_list,
                        owner_name=full_name,
                        action_message="New Risk has been Created"
                    )

    body = build_email_template("New Risk Created", content)

    create_email_job(db, fh, cc_emails, subject, body, created_by=risk.risk_owner_id)
    
    
    
## --------------------------------------------Common Function for Approval---------------------------------------------------------

def send_function_approval_email_seq(db: Session, risk_register_id: int,seq: int):
    
    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_register_id == risk_register_id
    ).first()

    if not risk:
        return
    
    ctx = get_risk_email_context(db, risk)         # comman function for email context healper

    function_list = ctx["function_name"]
    owner = ctx["owner_email"]
    full_name = ctx["owner_name"]

    fh = ctx["fh"]
    rm = ctx["rm"]
    rh = ctx["rh"]
    if seq == 1:
        to_emails = list(set(rm))
        cc_emails = list(set(fh + owner)- set(to_emails))
        subject = f"Risk Updated by Function Head - {risk.risk_id}"
        action_msg = "Risk has been Approved by Functional Head."
        
        template_title = "Function Head Approval"
        created_by = risk.risk_function_head_approval_by
        
    elif seq == 2:
        to_emails = list(set(rh))
        cc_emails = list(set(owner + fh + rm)- set(to_emails))
        subject = f"Risk approved by Risk Manager - {risk.risk_id}"
        action_msg = "Risk has been Approved by Risk Manager."
        
        template_title = "Risk Manager Approval"
        created_by = risk.risk_manager_approval_by
        
    else:
        treatments = db.execute(
            text(f"""
                SELECT DISTINCT action_owner_id
                FROM {SCHEMA}.risk_treatment
                WHERE risk_id = :risk_id
                AND is_deleted = 0
                AND action_owner_id IS NOT NULL
            """),
            {"risk_id": risk.risk_id}
        ).fetchall()

        action_owner_emails = []
        for row in treatments:
            owner_user = get_emails_by_user_ids(db,[row.action_owner_id])

            if owner_user and owner_user.get("email"):
                action_owner_emails.append(
                    owner_user["email"]
                )

        to_emails = list(set(owner + action_owner_emails))
        cc_emails = list(set(fh + rm + rh)- set(to_emails))
        subject = f"Risk approved by Risk Head - {risk.risk_id}"
        action_msg = "Risk has been Approved by Risk Head."
        
        template_title = "Risk Head Approval"
        created_by = risk.risk_head_approval_by
        
    content = build_risk_details_html(
            risk=risk,
            function_name=function_list,
            owner_name=full_name,
            action_message=action_msg
        )

    body = build_email_template(template_title, content)

    create_email_job(db, to_emails, cc_emails, subject, body, created_by=created_by)




# # EVENT 2: FUNCTION HEAD APPROVAL (TO: RM, CC: FH, RH, RO)

# def send_function_head_approval_email(db: Session, risk_register_id: int):

#     risk = db.query(RiskRegister).filter(
#         RiskRegister.risk_register_id == risk_register_id
#     ).first()

#     if not risk:
#         return
    
#     ctx = get_risk_email_context(db, risk)         # comman function for email context healper

#     function_list = ctx["function_name"]
#     owner = ctx["owner_email"]
#     full_name = ctx["owner_name"]

#     fh = ctx["fh"]
#     rm = ctx["rm"]
#     # rh = ctx["rh"]

#     to_emails = list(set(rm))
#     cc_emails = list(set(fh + owner)- set(to_emails))

#     subject = f"Risk Updated by Function Head - {risk.risk_id}"
#     content = build_risk_details_html(
#             risk=risk,
#             function_name=function_list,
#             owner_name=full_name,
#             action_message="Risk has been Approved by Functional Head."
#         )

#     body = build_email_template("Function Head Approval", content)

#     create_email_job(db, to_emails, cc_emails, subject, body, created_by=risk.risk_function_head_approval_by)
    


# # EVENT 3: RISK MANAGER ACTION (TO: RH, CC:FH,RM, RO)

# def send_risk_manager_email(db: Session, risk_register_id: int):

#     risk = db.query(RiskRegister).filter(
#         RiskRegister.risk_register_id == risk_register_id
#     ).first()

#     if not risk:
#         return

#     ctx = get_risk_email_context(db, risk)

#     function_list = ctx["function_name"]
#     owner = ctx["owner_email"]
#     full_name = ctx["owner_name"]

#     fh = ctx["fh"]
#     rm = ctx["rm"]
#     rh = ctx["rh"]

#     to_emails = list(set(rh))

#     cc_emails = list(set(owner + fh + rm)- set(to_emails))

#     subject = f"Risk approved by Risk Manager - {risk.risk_id}"

#     content = build_risk_details_html(
#                     risk=risk,
#                     function_name=function_list,
#                     owner_name=full_name,
#                     action_message="Risk has been Approved by Risk Manager."
#                 )

#     body = build_email_template("Risk Manager Approval", content)

#     create_email_job(db, to_emails, cc_emails, subject, body, created_by=risk.risk_manager_approval_by)


# # EVENT 4: RISK HEAD ACTION (TO: RO, CC: FH,RM,RO)

# def send_risk_head_email(db: Session, risk_register_id: int):

#     risk = db.query(RiskRegister).filter(
#         RiskRegister.risk_register_id == risk_register_id
#     ).first()

#     if not risk:
#         return

#     ctx = get_risk_email_context(db, risk)

#     function_list = ctx["function_name"]
#     owner = ctx["owner_email"]
#     full_name = ctx["owner_name"]

#     fh = ctx["fh"]
#     rm = ctx["rm"]
#     rh = ctx["rh"]
    
#     treatments = db.execute(
#         text(f"""
#             SELECT DISTINCT action_owner_id
#             FROM {SCHEMA}.risk_treatment
#             WHERE risk_id = :risk_id
#             AND is_deleted = 0
#             AND action_owner_id IS NOT NULL
#         """),
#         {"risk_id": risk.risk_id}
#     ).fetchall()

#     action_owner_emails = []
#     for row in treatments:
#         owner_user = get_emails_by_user_ids(db,[row.action_owner_id])

#         if owner_user and owner_user.get("email"):
#             action_owner_emails.append(
#                 owner_user["email"]
#             )

#     to_emails = list(set(owner + action_owner_emails))
#     cc_emails = list(set(fh + rm + rh)- set(to_emails))

#     subject = f"Risk approved by Risk Head - {risk.risk_id}"

#     content = build_risk_details_html(
#                             risk=risk,
#                             function_name=function_list,
#                             owner_name=full_name,
#                             action_message="Risk has been Approved by Risk Head."
#                         )

#     body = build_email_template("Risk Head Approval", content)

#     create_email_job(db, to_emails, cc_emails, subject, body, created_by=risk.risk_head_approval_by)
    
    
# EVENT 5: SEND TREATMENT EMAIL AFTER FULL APPROVAL

def send_treatment_email_after_approval(db: Session, risk_register_id: int):
    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_register_id == risk_register_id,
        RiskRegister.is_deleted == 0
    ).first()

    if not risk:
        print("Risk not found")
        return

    # Send only after all approvals completed
    if not (
        risk.risk_function_head_approval_status == 1 and
        risk.risk_manager_approval_status == 1 and
        risk.risk_head_approval_status == 1
    ):
        print("Approval not completed")
        return

    # ---------------- GET TREATMENTS ----------------
    treatments = db.execute(
        text(f"""
            SELECT
                risk_treatment_id,
                risk_description_id,
                risk_id,
                action_owner_id,
                action_plan,
                target_date,
                progress
            FROM {SCHEMA}.risk_treatment
            WHERE risk_id = :risk_id
            AND is_deleted = 0
        """),
        {"risk_id": risk.risk_id}
    ).fetchall()

    if not treatments:
        print("No treatments found")
        return

    # ---------------- COMMON DATA ----------------

    function_list = get_deptname_by_id(db, [risk.dept_id])

    risk_owner_data = get_emails_by_user_ids(db,[risk.risk_owner_id])

    full_name = (
        f"{risk_owner_data.get('first_name') or ''} "
        f"{risk_owner_data.get('last_name') or ''}"
    ).strip()

    # ---------------- COMMON CC USERS ----------------

    fh = get_users_by_role_name_fd(db,"Functional Head",risk.dept_id)

    rm = get_users_by_role_name(db,"Risk Manager")

    rh = get_users_by_role_name(db,"Risk Head")

    cc_list = list(set(fh + rm + rh))

    # ---------------- GROUP TREATMENTS BY ACTION OWNER ----------------

    owner_treatments = {}

    for treatment in treatments:
        owner_treatments.setdefault(
            treatment.action_owner_id,
            []
        ).append(treatment)

    # ---------------- SEND EMAIL TO EACH OWNER ----------------

    for owner_id, owner_plans in owner_treatments.items():

        owner_user = get_emails_by_user_ids(db,[owner_id])

        if not owner_user:
            continue

        to_emails = [owner_user["email"]]

        cc_emails = list(set(cc_list) - set(to_emails) )

        owner_name = (
            f"{owner_user.get('first_name') or ''} "
            f"{owner_user.get('last_name') or ''}"
        ).strip()

        treatment_rows = ""

        for plan in owner_plans:

            target_date = (
                plan.target_date.strftime("%d-%b-%Y")
                if plan.target_date
                else ""
            )

            treatment_rows += f"""
            <tr>
                <td>{plan.action_plan}</td>
                <td>{target_date}</td>
                <td>{plan.progress}%</td>
            </tr>
            """

        subject = (
            f"Action Required: Risk Treatment "
            f"Assignment - {risk.risk_id}"
        )

        body = f"""
        <html>
        <body style="font-family: Arial; background:#f4f6f8; padding:20px;">
            <table width="100%" style="background:white; padding:20px; border-radius:8px;">
                <tr>
                    <td>
                        <h2 style="color:#2c3e50;">Risk Treatment Assignment</h2>

                        <p>Dear {owner_name},</p>

                        <p>
                            The following risk has been fully approved and the below treatment actions have been assigned to you.
                        </p>

                        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
                            <tr><td><b>Risk ID</b></td><td>{risk.risk_id}</td></tr>
                            <tr><td><b>Functional Risk</b></td><td>{function_list}</td></tr>
                            <tr><td><b>Risk Owner</b></td><td>{full_name}</td></tr>
                            <tr><td><b>Risk Title</b></td><td>{risk.risk_name}</td></tr>
                            <tr><td><b>Financial Year</b></td><td>{risk.financial_year}</td></tr>
                        </table>

                        <br>

                        <table border="1" cellpadding="8" cellspacing="0" width="100%" style="border-collapse:collapse;">
                            <tr style="background:#2c3e50; color:white;">
                                <th>Action Plan</th>
                                <th>Target Date</th>
                                <th>Progress</th>
                            </tr>
                            {treatment_rows}
                        </table>

                        <p style="margin-top:20px;">
                            Kindly take necessary action within the defined timeline.
                        </p>

                        <p>
                            Regards,<br>
                            Enterprise Risk Management System
                        </p>
                    </td>
                </tr>
            </table>
        </body>
        </html>
        """

        create_email_job(db,to_emails,cc_emails,subject,body,created_by=risk.risk_head_approval_by)

    # print("Treatment Email Triggered")
    
    
#EVENT LAST: SEND NOTIFICATION TO ACTION OWNER THAT ACTION IS APPROVED OR REJECTED
def send_action_approve_reject_email(db: Session, treatment: RiskTreatment):
    risk = db.query(RiskRegister).filter(
        RiskRegister.risk_id == treatment.risk_id
    ).first()
    
    if not risk:
        return
    
    function_list = get_deptname_by_id(db, [risk.dept_id])
    user_data = get_emails_by_user_ids(db, [risk.risk_owner_id])
    
    to_owner = [user_data["email"]]
    full_name = f"{user_data.get('first_name') or ''} {user_data.get('last_name') or ''}".strip()
    
    user_data_action = get_emails_by_user_ids(db, [treatment.action_owner_id])
    
    to_action = [user_data_action["email"]]
    full_name_action = f"{user_data_action.get('first_name') or ''} {user_data_action.get('last_name') or ''}".strip()
    
    fh = get_users_by_role_name_fd(db, "Functional Head",risk.dept_id)
    rm = get_users_by_role_name(db, "Risk Manager")
    rh = get_users_by_role_name(db, "Risk Head")

    cc_emails = list(set(to_owner + rm + rh + fh) - set(to_action))
    
    status = ""
    if treatment.approval_status == 1:
        subject = f"Risk action approved - {risk.risk_id},{treatment.action_plan}"
        status = "approved"
    else:
        subject = f"Risk action rejected - {risk.risk_id},{treatment.action_plan}"
        status = "rejected"
        
    content = f"""
    <p>Dear Team,</p>

    <p>Action plan has been {status}. Details are:</p>
    
    <table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse;">
        <tr><td><b>Risk ID</b></td><td>{risk.risk_id}</td></tr>
        <tr><td><b>Functional Risk</b></td><td>{function_list}</td></tr>
        <tr><td><b>Risk Owner</b></td><td>{full_name}</td></tr>
        <tr><td><b>Action Owner</b></td><td>{full_name_action}</td></tr>
        <tr><td><b>Risk Title</b></td><td>{risk.risk_name}</td></tr>
        <tr><td><b>Financial Year</b></td><td>{risk.financial_year}</td></tr>
        <tr><td><b>Action Plan</b></td><td>{treatment.action_plan}</td></tr>
    </table>

    <p>Please review the action and initiate the required action.</p>

    <p>Regards,<br>Enterprise Risk Management System</p>
    """
    body = build_email_template("Action plan has been " + status, content)
    
    create_email_job(db, to_action, cc_emails, subject, body, created_by=risk.risk_owner_id)
    
    
    
    
#-------------------------------Reset Password ------------


def send_forgot_password_email(db: Session, user: User):

    encrypted_email = encrypt_text(user.email)
    reset_url = f"{settings.MAIN_URL}?code={encrypted_email}"
    
    subject = "Reset Password"
    content = f"""
        <p>Hello {user.first_name} {user.last_name},</p>

        <p>
            We received a request to reset your password.
        </p>

        <p>
            <a href="{reset_url}">
                Click here to reset your password
            </a>
        </p>

        <p>
            If you didn't request this, you can safely ignore this email.
        </p>
        
        <p>Regards,<br>Enterprise Risk Management System</p>
    """

    body = build_email_template(
        "Reset Password",
        content
    )

    create_email_job(db=db,to_list=[user.email],cc_list=[],subject=subject,body=body,created_by=user.id)
    
    