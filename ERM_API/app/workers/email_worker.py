import time
import traceback
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.core.config import settings

from app.core.database import SessionLocal
from app.services.email_sender import send_email

SCHEMA = settings.DB_SCHEMA     # fetching schema name from config to use in raw SQL queries

print("======================================")
print(" Email Worker Started Successfully ")
print(" Running every 10 second...")
print("======================================\n")


def email_worker():

    while True:

        db: Session = SessionLocal()

        try:
            jobs = db.execute(text(f"""
                SELECT *
                FROM {SCHEMA}.mst_email_job
                WHERE
                    is_deleted = 0
                    AND (
                        send_status IS NULL
                        OR send_status = 'FAILED'
                        OR send_status = 'New'
                    )
                    AND (next_attempt_at IS NULL OR next_attempt_at <= NOW())
                ORDER BY email_job_id
                LIMIT 10
            """)).fetchall()

            if not jobs:
                print(f"[{datetime.now()}] No pending emails...")
                db.close()
                time.sleep(10)                                          # Sleep before next check
                continue

            print(f"[{datetime.now()}] Found {len(jobs)} pending email(s)")
            
            for job in jobs:
                print(f"\n==============================")
                print(f"Processing Job ID: {job.email_job_id}")
                print(f"TO: {job.email_to}")
                print(f"CC: {job.email_cc}")
                print(f"==============================")

                success = send_email(db, job)

                # new_attempt = job.send_attempts + 1
                new_attempt = (job.send_attempts or 0) + 1
                
                if success:
                    print(" Email sent successfully")

                    db.execute(text(f"""
                        UPDATE {SCHEMA}.mst_email_job
                        SET send_status = 'SUCCESS',
                            send_attempts = :attempt
                        WHERE email_job_id = :id
                    """), {"attempt": new_attempt, "id": job.email_job_id})

                else:
                    print(" Email failed")

                    if new_attempt >= job.total_attempts:
                        db.execute(text(f"""
                            UPDATE {SCHEMA}.mst_email_job
                            SET send_status = 'FAILED_FINAL',
                                send_attempts = :attempt
                            WHERE email_job_id = :id
                        """), {"attempt": new_attempt, "id": job.email_job_id})

                    else:
                        db.execute(text(f"""
                            UPDATE {SCHEMA}.mst_email_job
                            SET send_status = 'FAILED',
                                send_attempts = :attempt,
                                next_attempt_at = NOW() + (:delay || ' milliseconds')::interval
                            WHERE email_job_id = :id
                        """), {
                            "attempt": new_attempt,
                            "delay": job.attempt_delay,
                            "id": job.email_job_id
                        })

            db.commit()

        except Exception as e:
            print("Worker error:", e)
            db.rollback()

        finally:
            db.close()

        time.sleep(10)           # ecah 10 second check for pending email jobs


if __name__ == "__main__":
    email_worker()