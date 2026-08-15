import os
import time

from app.database import connect

CHECK_RETENTION_DAYS = int(os.environ.get("CHECK_RETENTION_DAYS", "90"))
SYSTEM_RETENTION_DAYS = int(os.environ.get("SYSTEM_RETENTION_DAYS", "90"))
MAINTENANCE_INTERVAL_SECONDS = int(os.environ.get("MAINTENANCE_INTERVAL_SECONDS", "86400"))


def run_cleanup():
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM sessions WHERE expires_at < NOW()")
            expired_sessions = cursor.rowcount
            cursor.execute(
                """
                DELETE FROM checks
                WHERE checked_at < NOW() - make_interval(days => %s)
                  AND id NOT IN (SELECT opening_check_id FROM incidents)
                  AND id NOT IN (SELECT closing_check_id FROM incidents WHERE closing_check_id IS NOT NULL)
                """,
                (CHECK_RETENTION_DAYS,),
            )
            checks = cursor.rowcount
            cursor.execute(
                """
                DELETE FROM system_health_samples
                WHERE checked_at < NOW() - make_interval(days => %s)
                  AND id NOT IN (SELECT opening_sample_id FROM system_incidents)
                  AND id NOT IN (SELECT closing_sample_id FROM system_incidents WHERE closing_sample_id IS NOT NULL)
                """,
                (SYSTEM_RETENTION_DAYS,),
            )
            samples = cursor.rowcount
            cursor.execute(
                """DELETE FROM notifications
                   WHERE status = 'SENT'
                     AND sent_at < NOW() - INTERVAL '90 days'"""
            )
            notifications = cursor.rowcount
    print(
        f"cleanup completed checks={checks} samples={samples} "
        f"sessions={expired_sessions} notifications={notifications}",
        flush=True,
    )


def main():
    print(
        f"maintenance started check_days={CHECK_RETENTION_DAYS} "
        f"system_days={SYSTEM_RETENTION_DAYS}",
        flush=True,
    )
    while True:
        try:
            run_cleanup()
        except Exception as error:
            print(f"cleanup failed: {error}", flush=True)
        time.sleep(MAINTENANCE_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
