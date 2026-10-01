import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from sqlalchemy.orm import Session
from sqlalchemy import text
import os
import logging
from logging.handlers import TimedRotatingFileHandler
import traceback
from app.core.config import settings

SCHEMA = settings.DB_SCHEMA


# =====================================================
# LOGGING CONFIGURATION
# =====================================================

LOG_FOLDER = "logs"
os.makedirs(LOG_FOLDER, exist_ok=True)

logger = logging.getLogger("email_service")
logger.setLevel(logging.INFO)

if not logger.handlers:
    log_handler = TimedRotatingFileHandler(
        filename=os.path.join(LOG_FOLDER, "email_service.log"),
        when="midnight",
        interval=1,
        backupCount=30,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(message)s"
    )

    log_handler.setFormatter(formatter)
    logger.addHandler(log_handler)

# function do the actual email sending using the email server details and job details, returns True if email sent successfully, otherwise False
def send_email(db: Session, job):
    try:
        logger.info(
            f"Process to send email. "
            f"Email Job ID={getattr(job, 'email_job_id', 'N/A')}"
        )

        server = db.execute(text(f"""
            SELECT *    
            FROM {SCHEMA}.email_server
            WHERE email_server_id = :id
            AND is_deleted = 0
        """), {"id": job.email_server_id}).fetchone()

        if not server:
            return False


        msg = MIMEMultipart()

        # FROM
        msg["From"] = server.outgoing_email_user

        # -------- TO ----------
        to_list = [x.strip() for x in job.email_to.split(",")] if job.email_to else []

        # -------- CC ----------
        cc_list = [x.strip() for x in job.email_cc.split(",")] if job.email_cc else []

        # -------- BCC ----------
        bcc_list = [x.strip() for x in job.email_bcc.split(",")] if job.email_bcc else []
        
        # Combine all receivers (VERY IMPORTANT)
        all_recipients = to_list + cc_list + bcc_list
        
        if not all_recipients:
            logger.warning(
                f"No recipients found. "
                f"Email Job ID={getattr(job, 'email_job_id', 'N/A')}"
            )
            return False, "No recipients found"

        logger.info(
            f"Recipients Count => "
            f"TO={len(to_list)}, "
            f"CC={len(cc_list)}, "
            f"BCC={len(bcc_list)}"
        )

        logger.info(f"TO: {', '.join(to_list)}")
        logger.info(f"CC: {', '.join(cc_list)}")
        

        msg["To"] = ", ".join(to_list)
        msg["Cc"] = ", ".join(cc_list)
        msg["Subject"] = job.email_subject

        msg.attach(
            MIMEText(job.email_body or "", "html")
        )

        if server.outgoing_email_port:
            smtp = smtplib.SMTP(server.outgoing_server_ip, server.outgoing_email_port)
        else:
            smtp = smtplib.SMTP(server.outgoing_server_ip)

        if server.outgoing_email_encryption == 1:
            smtp.starttls()

        if server.outgoing_email_user and server.outgoing_email_password:
            smtp.login(server.outgoing_email_user, server.outgoing_email_password)
        


        smtp.sendmail(
            server.outgoing_email_user,
            all_recipients,
            msg.as_string()
        )
        logger.info(
            f"Email sent successfully. "
            f"Subject='{job.email_subject}' "
            f"Recipients={len(all_recipients)}"
        )

        smtp.quit()

        return True

    except Exception as e:
        logger.exception(
            f"Email send failed. "
            f"Email Job ID={getattr(job, 'email_job_id', 'N/A')} "
            f"Error={str(e)}"
        )
        return False
    
    



##------------------using Static------------

# import smtplib
# from email.mime.text import MIMEText
# from email.mime.multipart import MIMEMultipart
# from sqlalchemy.orm import Session
# from sqlalchemy import text
# import os
# import logging
# from logging.handlers import TimedRotatingFileHandler
# import traceback

# # from app.core.config import settings


# # =====================================================
# # LOGGING CONFIGURATION
# # =====================================================

# LOG_FOLDER = "logs"
# os.makedirs(LOG_FOLDER, exist_ok=True)

# logger = logging.getLogger("email_service")
# logger.setLevel(logging.INFO)

# if not logger.handlers:
#     log_handler = TimedRotatingFileHandler(
#         filename=os.path.join(LOG_FOLDER, "email_service.log"),
#         when="midnight",
#         interval=1,
#         backupCount=30,
#         encoding="utf-8"
#     )

#     formatter = logging.Formatter(
#         "%(asctime)s | %(levelname)s | %(message)s"
#     )

#     log_handler.setFormatter(formatter)
#     logger.addHandler(log_handler)

# # function do the actual email sending using the email server details and job details, returns True if email sent successfully, otherwise False

# def send_email(job):

#     try:
#         logger.info(
#             f"Process to send email. "
#             f"Email Job ID={getattr(job, 'email_job_id', 'N/A')}"
#         )        
        
#         # SMTP Configuration
#         server = {
#             "SMTP_SERVER": "mail.alethelabs.co.in",
#             "SMTP_PORT": 587,
#             "outgoing_email_encryption": 1,
#             "EMAIL_FROM": "jasmin.babariya@alethelabs.co.in",
#             "outgoing_email_user": "jasmin.babariya@alethelabs.co.in",
#             "outgoing_email_password": 'Bholu@48jasmin'
#         }
        

#         msg = MIMEMultipart()

#         msg["From"] = server['EMAIL_FROM']

#         to_list = [x.strip() for x in job.email_to.split(",")] if job.email_to else []
#         cc_list = [x.strip() for x in job.email_cc.split(",")] if job.email_cc else []
#         bcc_list = [x.strip() for x in job.email_bcc.split(",")] if hasattr(job, "email_bcc") and job.email_bcc else []
        
#         recipients = to_list + cc_list + bcc_list
        
#         if not recipients:
#             logger.warning(
#                 f"No recipients found. "
#                 f"Email Job ID={getattr(job, 'email_job_id', 'N/A')}"
#             )
#             return False, "No recipients found"

#         logger.info(
#             f"Recipients Count => "
#             f"TO={len(to_list)}, "
#             f"CC={len(cc_list)}, "
#             f"BCC={len(bcc_list)}"
#         )

#         logger.info(f"TO: {', '.join(to_list)}")
#         logger.info(f"CC: {', '.join(cc_list)}")
        

#         msg["To"] = ", ".join(to_list)
#         msg["Cc"] = ", ".join(cc_list)
#         msg["Subject"] = job.email_subject

#         msg.attach(
#             MIMEText(job.email_body or "", "html")
#         )

        
#         if server['SMTP_PORT']:
#             smtp = smtplib.SMTP(
#                 server['SMTP_SERVER'],
#                 server['SMTP_PORT']
#             )
            
#         else:
#             smtp = smtplib.SMTP(server['SMTP_SERVER'])
        
#         if server['outgoing_email_encryption'] == 1:
#             smtp.starttls()


#         if server["outgoing_email_user"] and server["outgoing_email_password"]:
#             smtp.login(
#                 server['outgoing_email_user'],
#                 server['outgoing_email_password']
#     )

#         result = smtp.sendmail(
#             server['EMAIL_FROM'],
#             recipients,
#             msg.as_string()
#         )
        
#         print("SMTP Result:", result)
        
#         logger.info(
#             f"Email sent successfully. "
#             f"Subject='{job.email_subject}' "
#             f"Recipients={len(recipients)}"
#         )

#         smtp.quit()

#         return True, "Email sent successfully"

#     except Exception as e:
#         logger.exception(
#             f"Email send failed. "
#             f"Email Job ID={getattr(job, 'email_job_id', 'N/A')} "
#             f"Error={str(e)}"
#         )
#         return False, str(e)
    
    
# SCHEMA = settings.DB_SCHEMA

# # function do the actual email sending using the email server details and job details, returns True if email sent successfully, otherwise False
# def send_email(db: Session, job):

#     server = db.execute(text(f"""
#         SELECT *
#         FROM {SCHEMA}.email_server
#         WHERE email_server_id = :id
#         AND is_deleted = 0
#     """), {"id": job.email_server_id}).fetchone()

#     if not server:
#         return False

#     try:
#         msg = MIMEMultipart()

#         # FROM
#         msg["From"] = server.outgoing_email_user

#         # -------- TO ----------
#         to_list = [x.strip() for x in job.email_to.split(",")] if job.email_to else []

#         # -------- CC ----------
#         cc_list = [x.strip() for x in job.email_cc.split(",")] if job.email_cc else []

#         # -------- BCC ----------
#         bcc_list = [x.strip() for x in job.email_bcc.split(",")] if job.email_bcc else []

#         # Add headers
#         msg["To"] = ", ".join(to_list)
#         msg["Cc"] = ", ".join(cc_list)
#         msg["Subject"] = job.email_subject

#         # Email body
#         msg.attach(MIMEText(job.email_body or "", "html"))

#         # Combine all receivers (VERY IMPORTANT)
#         all_recipients = to_list + cc_list + bcc_list

#         smtp = smtplib.SMTP(server.outgoing_server_ip, server.outgoing_email_port)

#         if server.outgoing_email_encryption == 1:
#             smtp.starttls()

#         smtp.login(server.outgoing_email_user, server.outgoing_email_password)

#         smtp.sendmail(
#             server.outgoing_email_user,
#             all_recipients,
#             msg.as_string()
#         )

#         smtp.quit()

#         return True

#     except Exception as e:
#         print("Email send error:")
#         traceback.print_exc()
#         return False