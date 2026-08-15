import os

import psycopg
from psycopg.rows import dict_row

from app.config import read_secret, require_production_value
from app.state_machine import transition_state


def connect():
    password = read_secret("POSTGRES_PASSWORD")
    require_production_value("POSTGRES_PASSWORD", password, min_length=20)
    return psycopg.connect(
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        user=os.environ["POSTGRES_USER"],
        password=password,
        dbname=os.environ["POSTGRES_DB"],
    )


def enqueue_system_notification(cursor, incident_id: int, event_type: str):
    cursor.execute(
        """
        INSERT INTO notifications (
            event_key, source_type, source_id, event_type
        )
        VALUES (%s, 'SYSTEM_INCIDENT', %s, %s)
        ON CONFLICT (event_key) DO NOTHING
        """,
        (f"system-{incident_id}-{event_type}", incident_id, event_type),
    )


def enqueue_monitor_notification(cursor, incident_id: int, event_type: str):
    cursor.execute(
        """
        INSERT INTO notifications (
            event_key, source_type, source_id, event_type
        )
        VALUES (%s, 'MONITOR_INCIDENT', %s, %s)
        ON CONFLICT (event_key) DO NOTHING
        """,
        (f"monitor-{incident_id}-{event_type}", incident_id, event_type),
    )


def record_system_health(samples: list[dict]):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            for sample in samples:
                cursor.execute(
                    """
                    INSERT INTO system_health_samples (
                        component, status, response_time_ms,
                        stream_jobs, pending_jobs, detail
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    (
                        sample["component"], sample["status"],
                        sample.get("response_time_ms"), sample.get("stream_jobs"),
                        sample.get("pending_jobs"), sample.get("detail", ""),
                    ),
                )
                sample_id = cursor.fetchone()["id"]
                cursor.execute(
                    """
                    INSERT INTO system_component_states (component)
                    VALUES (%s)
                    ON CONFLICT (component) DO NOTHING
                    """,
                    (sample["component"],),
                )
                cursor.execute(
                    "SELECT * FROM system_component_states WHERE component = %s FOR UPDATE",
                    (sample["component"],),
                )
                state = cursor.fetchone()
                transition = transition_state(
                    state["current_status"],
                    state["consecutive_failures"],
                    state["consecutive_successes"],
                    sample["status"] == "UP",
                )

                cursor.execute(
                    """
                    UPDATE system_component_states
                    SET current_status = %s, consecutive_failures = %s,
                        consecutive_successes = %s, updated_at = NOW()
                    WHERE component = %s
                    """,
                    (
                        transition.status,
                        transition.failures,
                        transition.successes,
                        sample["component"],
                    ),
                )
                if transition.open_incident:
                    cursor.execute(
                        """
                        INSERT INTO system_incidents (component, opening_sample_id)
                        SELECT %s, %s
                        WHERE NOT EXISTS (
                            SELECT 1 FROM system_incidents
                            WHERE component = %s AND resolved_at IS NULL
                        )
                        RETURNING id
                        """,
                        (sample["component"], sample_id, sample["component"]),
                    )
                    incident = cursor.fetchone()
                    if incident:
                        enqueue_system_notification(cursor, incident["id"], "OPENED")
                if transition.resolve_incident:
                    cursor.execute(
                        """
                        UPDATE system_incidents
                        SET resolved_at = NOW(), closing_sample_id = %s
                        WHERE component = %s AND resolved_at IS NULL
                        RETURNING id
                        """,
                        (sample_id, sample["component"]),
                    )
                    incident = cursor.fetchone()
                    if incident:
                        enqueue_system_notification(cursor, incident["id"], "RESOLVED")


def claim_notification():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT notifications.*,
                       system_incidents.component,
                       monitors.name AS monitor_name,
                       monitors.monitor_type,
                       monitors.url::text AS monitor_url,
                       projects.name AS project_name,
                       COALESCE(system_incidents.started_at, monitor_incidents.started_at) AS started_at,
                       COALESCE(system_incidents.resolved_at, monitor_incidents.resolved_at) AS resolved_at,
                       CASE
                           WHEN notifications.source_type = 'SYSTEM_INCIDENT'
                               THEN system_opening.detail
                           WHEN monitor_opening.error_message IS NOT NULL
                               THEN monitor_opening.error_message
                           WHEN monitor_opening.status_code IS NULL
                               THEN 'No response received'
                           ELSE 'Expected HTTP status ' || monitors.expected_status_code ||
                                ', received ' || monitor_opening.status_code
                       END AS cause
                FROM notifications
                LEFT JOIN system_incidents
                  ON notifications.source_type = 'SYSTEM_INCIDENT'
                 AND system_incidents.id = notifications.source_id
                LEFT JOIN system_health_samples AS system_opening
                  ON system_opening.id = system_incidents.opening_sample_id
                LEFT JOIN incidents AS monitor_incidents
                  ON notifications.source_type = 'MONITOR_INCIDENT'
                 AND monitor_incidents.id = notifications.source_id
                LEFT JOIN checks AS monitor_opening
                  ON monitor_opening.id = monitor_incidents.opening_check_id
                LEFT JOIN monitors
                  ON monitors.id = monitor_incidents.monitor_id
                LEFT JOIN projects
                  ON projects.id = monitors.project_id
                WHERE (
                    (
                        notifications.status = 'PENDING'
                        AND notifications.next_attempt_at <= NOW()
                    ) OR (
                        notifications.status = 'PROCESSING'
                        AND notifications.locked_at <= NOW() - INTERVAL '5 minutes'
                    )
                )
                ORDER BY notifications.created_at
                FOR UPDATE OF notifications SKIP LOCKED
                LIMIT 1
                """
            )
            notification = cursor.fetchone()
            if notification is None:
                return None
            cursor.execute(
                """
                UPDATE notifications
                SET status = 'PROCESSING', attempts = attempts + 1,
                    locked_at = NOW(), last_error = NULL
                WHERE id = %s
                RETURNING attempts
                """,
                (notification["id"],),
            )
            notification["attempts"] = cursor.fetchone()["attempts"]
            return notification


def mark_notification_sent(notification_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notification_delivery_attempts (
                    notification_id, succeeded
                ) VALUES (%s, TRUE)
                """,
                (notification_id,),
            )
            cursor.execute(
                """
                UPDATE notifications
                SET status = 'SENT', sent_at = NOW(), locked_at = NULL,
                    last_error = NULL
                WHERE id = %s
                """,
                (notification_id,),
            )


def mark_notification_failed(notification_id: int, attempts: int, error: str):
    delay_seconds = min(300, 10 * (2 ** max(0, attempts - 1)))
    final_status = "FAILED" if attempts >= 5 else "PENDING"
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notification_delivery_attempts (
                    notification_id, succeeded, error_message
                ) VALUES (%s, FALSE, %s)
                """,
                (notification_id, error[:1000]),
            )
            cursor.execute(
                """
                UPDATE notifications
                SET status = %s, last_error = %s, locked_at = NULL,
                    next_attempt_at = NOW() + make_interval(secs => %s)
                WHERE id = %s
                """,
                (final_status, error[:1000], delay_seconds, notification_id),
            )


def get_notification_summary():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) FILTER (WHERE status = 'SENT') AS sent,
                       COUNT(*) FILTER (WHERE status IN ('PENDING', 'PROCESSING')) AS pending,
                       COUNT(*) FILTER (WHERE status = 'FAILED') AS failed,
                       MAX(sent_at) AS last_sent_at
                FROM notifications
                """
            )
            summary = cursor.fetchone()
            cursor.execute(
                """
                SELECT succeeded, error_message, attempted_at
                FROM notification_delivery_attempts
                ORDER BY attempted_at DESC, id DESC
                LIMIT 1
                """
            )
            latest = cursor.fetchone()
            summary["current_status"] = (
                "OPERATIONAL" if latest and latest["succeeded"]
                else "DEGRADED" if latest
                else "UNKNOWN"
            )
            summary["last_attempt_at"] = latest["attempted_at"] if latest else None
            cursor.execute(
                """
                SELECT error_message, attempted_at
                FROM notification_delivery_attempts
                WHERE succeeded = FALSE
                ORDER BY attempted_at DESC, id DESC
                LIMIT 1
                """
            )
            failure = cursor.fetchone()
            summary["last_error"] = failure["error_message"] if failure else None
            summary["last_failure_at"] = failure["attempted_at"] if failure else None
            return summary


def list_notification_attempts(limit: int = 50):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT attempts.id,
                       attempts.notification_id,
                       attempts.succeeded,
                       attempts.error_message,
                       attempts.attempted_at,
                       notifications.source_type,
                       notifications.event_type,
                       notifications.status AS notification_status,
                       COALESCE(projects.name, 'Netsuro') AS project_name,
                       COALESCE(monitors.name, system_incidents.component) AS subject_name
                FROM notification_delivery_attempts AS attempts
                JOIN notifications
                  ON notifications.id = attempts.notification_id
                LEFT JOIN incidents AS monitor_incidents
                  ON notifications.source_type = 'MONITOR_INCIDENT'
                 AND monitor_incidents.id = notifications.source_id
                LEFT JOIN monitors
                  ON monitors.id = monitor_incidents.monitor_id
                LEFT JOIN projects
                  ON projects.id = monitors.project_id
                LEFT JOIN system_incidents
                  ON notifications.source_type = 'SYSTEM_INCIDENT'
                 AND system_incidents.id = notifications.source_id
                ORDER BY attempts.attempted_at DESC, attempts.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            return cursor.fetchall()


def retry_failed_notification(notification_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE notifications
                SET status = 'PENDING', attempts = 0,
                    next_attempt_at = NOW(), locked_at = NULL,
                    last_error = NULL
                WHERE id = %s AND status = 'FAILED'
                RETURNING id
                """,
                (notification_id,),
            )
            return cursor.fetchone() is not None


def list_system_incidents():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT incidents.*, states.current_status
                FROM system_incidents AS incidents
                LEFT JOIN system_component_states AS states
                  ON states.component = incidents.component
                ORDER BY incidents.started_at DESC, incidents.id DESC
                """
            )
            return cursor.fetchall()


def get_system_incident(incident_id: int):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT incidents.*, states.current_status,
                       opening.detail AS opening_detail,
                       opening.status AS opening_status,
                       opening.checked_at AS opening_checked_at,
                       closing.checked_at AS closing_checked_at
                FROM system_incidents AS incidents
                LEFT JOIN system_component_states AS states
                  ON states.component = incidents.component
                JOIN system_health_samples AS opening
                  ON opening.id = incidents.opening_sample_id
                LEFT JOIN system_health_samples AS closing
                  ON closing.id = incidents.closing_sample_id
                WHERE incidents.id = %s
                """,
                (incident_id,),
            )
            incident = cursor.fetchone()
            if incident is None:
                return None
            cursor.execute(
                """
                SELECT id, component, status, response_time_ms,
                       stream_jobs, pending_jobs, detail, checked_at
                FROM system_health_samples
                WHERE component = %s
                  AND checked_at >= %s - INTERVAL '3 minutes'
                  AND checked_at <= COALESCE(%s, NOW()) + INTERVAL '2 minutes'
                ORDER BY checked_at DESC
                LIMIT 50
                """,
                (incident["component"], incident["started_at"], incident["resolved_at"]),
            )
            return {"incident": incident, "samples": cursor.fetchall()}


def get_system_health_history(component: str, hours: int):
    bucket = "5 minutes" if hours == 24 else "1 hour" if hours == 168 else "6 hours"
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT COUNT(*) AS total_samples,
                       COALESCE(ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'UP') /
                           NULLIF(COUNT(*), 0), 2), 0) AS availability,
                       COUNT(*) FILTER (WHERE status != 'UP') AS failures,
                       ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms,
                       ROUND(AVG(stream_jobs)::numeric, 2) AS avg_stream_jobs,
                       MAX(stream_jobs) AS max_stream_jobs,
                       MAX(pending_jobs) AS max_pending_jobs
                FROM system_health_samples
                WHERE component = %s
                  AND checked_at >= NOW() - make_interval(hours => %s)
                """,
                (component, hours),
            )
            summary = cursor.fetchone()
            cursor.execute(
                """
                SELECT date_bin(%s::interval, checked_at, TIMESTAMPTZ '2000-01-01') AS bucket,
                       ROUND(100.0 * COUNT(*) FILTER (WHERE status = 'UP') /
                           NULLIF(COUNT(*), 0), 2) AS availability,
                       ROUND(AVG(response_time_ms)::numeric, 2) AS avg_response_time_ms,
                       ROUND(AVG(stream_jobs)::numeric, 2) AS avg_stream_jobs,
                       MAX(stream_jobs) AS max_stream_jobs,
                       MAX(pending_jobs) AS max_pending_jobs,
                       COUNT(*) FILTER (WHERE status = 'UP') AS up_samples,
                       COUNT(*) FILTER (WHERE status != 'UP') AS failed_samples,
                       COUNT(*) AS samples
                FROM system_health_samples
                WHERE component = %s
                  AND checked_at >= NOW() - make_interval(hours => %s)
                GROUP BY bucket
                ORDER BY bucket
                """,
                (bucket, component, hours),
            )
            points = cursor.fetchall()
            cursor.execute(
                """
                SELECT component, status, response_time_ms, stream_jobs,
                       pending_jobs, detail, checked_at
                FROM system_health_samples
                WHERE component = %s
                ORDER BY checked_at DESC
                LIMIT 20
                """,
                (component,),
            )
            return {"component": component, "summary": summary, "points": points, "recent_samples": cursor.fetchall()}


def create_monitor(data: dict):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO monitors (
                    project_id,
                    monitor_type,
                    name,
                    url,
                    interval_seconds,
                    timeout_seconds,
                    expected_status_code,
                    heartbeat_grace_seconds,
                    heartbeat_token_hash,
                    heartbeat_token_rotated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        CASE WHEN %s IS NULL THEN NULL ELSE NOW() END)
                RETURNING *
                """,
                (
                    data["project_id"],
                    data["monitor_type"],
                    data["name"],
                    data["url"],
                    data["interval_seconds"],
                    data["timeout_seconds"],
                    data["expected_status_code"],
                    data["heartbeat_grace_seconds"],
                    data.get("heartbeat_token_hash"),
                    data.get("heartbeat_token_hash"),
                ),
            )
            return cursor.fetchone()


def list_monitors():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute("SELECT * FROM monitors ORDER BY id")
            return cursor.fetchall()


def get_monitor(monitor_id: int):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT monitors.*, projects.is_archived AS project_is_archived
                FROM monitors
                JOIN projects ON projects.id = monitors.project_id
                WHERE monitors.id = %s
                """,
                (monitor_id,),
            )
            return cursor.fetchone()


def update_monitor(monitor_id: int, changes: dict):
    allowed_columns = {
        "project_id",
        "name",
        "url",
        "interval_seconds",
        "timeout_seconds",
        "expected_status_code",
        "heartbeat_grace_seconds",
        "is_active",
        "is_archived",
    }
    columns = [column for column in changes if column in allowed_columns]
    assignments = ", ".join(f"{column} = %s" for column in columns)
    values = [changes[column] for column in columns]

    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE monitors
                SET {assignments}, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (*values, monitor_id),
            )
            return cursor.fetchone()


def create_check(data: dict):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM monitors WHERE id = %s FOR UPDATE",
                (data["monitor_id"],),
            )
            monitor = cursor.fetchone()
            if monitor is None:
                raise ValueError("monitor not found")

            cursor.execute(
                """
                INSERT INTO checks (
                    job_id,
                    monitor_id,
                    status_code,
                    response_time_ms,
                    succeeded,
                    error_message
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (job_id) DO NOTHING
                RETURNING *
                """,
                (
                    data.get("job_id"),
                    data["monitor_id"],
                    data["status_code"],
                    data["response_time_ms"],
                    data["succeeded"],
                    data["error_message"],
                ),
            )
            saved_check = cursor.fetchone()

            if saved_check is None:
                cursor.execute(
                    "SELECT * FROM checks WHERE job_id = %s",
                    (data["job_id"],),
                )
                return cursor.fetchone()

            transition = transition_state(
                monitor["current_status"],
                monitor["consecutive_failures"],
                monitor["consecutive_successes"],
                saved_check["succeeded"],
            )

            cursor.execute(
                """
                UPDATE monitors
                SET current_status = %s,
                    consecutive_failures = %s,
                    consecutive_successes = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (
                    transition.status,
                    transition.failures,
                    transition.successes,
                    data["monitor_id"],
                ),
            )

            if transition.open_incident:
                cursor.execute(
                    """
                    INSERT INTO incidents (monitor_id, opening_check_id)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (data["monitor_id"], saved_check["id"]),
                )
                incident = cursor.fetchone()
                enqueue_monitor_notification(cursor, incident["id"], "OPENED")

            if transition.resolve_incident:
                cursor.execute(
                    """
                    UPDATE incidents
                    SET resolved_at = NOW(), closing_check_id = %s
                    WHERE monitor_id = %s AND resolved_at IS NULL
                    RETURNING id
                    """,
                    (saved_check["id"], data["monitor_id"]),
                )
                incident = cursor.fetchone()
                if incident:
                    enqueue_monitor_notification(cursor, incident["id"], "RESOLVED")

            return saved_check


def list_checks(monitor_id: int):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM checks
                WHERE monitor_id = %s
                ORDER BY checked_at DESC, id DESC
                """,
                (monitor_id,),
            )
            return cursor.fetchall()


def list_due_monitors():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT monitors.*
                FROM monitors
                JOIN projects ON projects.id = monitors.project_id
                LEFT JOIN LATERAL (
                    SELECT checked_at
                    FROM checks
                    WHERE checks.monitor_id = monitors.id
                    ORDER BY checked_at DESC
                    LIMIT 1
                ) AS latest_check ON TRUE
                WHERE monitors.is_active = TRUE
                  AND monitors.is_archived = FALSE
                  AND projects.is_archived = FALSE
                  AND monitors.monitor_type = 'HTTP'
                  AND (
                    latest_check.checked_at IS NULL
                    OR latest_check.checked_at <= NOW() -
                       make_interval(secs => monitors.interval_seconds)
                  )
                ORDER BY monitors.id
                """
            )
            return cursor.fetchall()


def list_incidents():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT * FROM incidents
                ORDER BY started_at DESC, id DESC
                """
            )
            return cursor.fetchall()


def list_dashboard_monitors():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT monitors.*,
                       latest_check.status_code AS latest_status_code,
                       latest_check.response_time_ms AS latest_response_time_ms,
                       latest_check.succeeded AS latest_succeeded,
                       latest_check.checked_at AS latest_checked_at
                FROM monitors
                LEFT JOIN LATERAL (
                    SELECT status_code, response_time_ms, succeeded, checked_at
                    FROM checks
                    WHERE checks.monitor_id = monitors.id
                    ORDER BY checked_at DESC, id DESC
                    LIMIT 1
                ) AS latest_check ON TRUE
                ORDER BY monitors.id
                """
            )
            return cursor.fetchall()


def list_due_heartbeat_monitors():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT monitors.*
                FROM monitors
                JOIN projects ON projects.id = monitors.project_id
                LEFT JOIN LATERAL (
                    SELECT checked_at
                    FROM checks
                    WHERE checks.monitor_id = monitors.id
                    ORDER BY checked_at DESC, id DESC
                    LIMIT 1
                ) AS latest_check ON TRUE
                WHERE monitors.monitor_type = 'HEARTBEAT'
                  AND monitors.is_active = TRUE
                  AND monitors.is_archived = FALSE
                  AND projects.is_archived = FALSE
                  AND COALESCE(monitors.last_heartbeat_at, monitors.created_at)
                      <= NOW() - make_interval(
                          secs => monitors.interval_seconds + monitors.heartbeat_grace_seconds
                      )
                  AND (
                      latest_check.checked_at IS NULL
                      OR latest_check.checked_at
                         <= NOW() - make_interval(secs => monitors.interval_seconds)
                  )
                ORDER BY monitors.id
                """
            )
            return cursor.fetchall()


def record_heartbeat(token_hash: str):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT monitors.id
                FROM monitors
                JOIN projects ON projects.id = monitors.project_id
                WHERE monitors.heartbeat_token_hash = %s
                  AND monitors.monitor_type = 'HEARTBEAT'
                  AND monitors.is_active = TRUE
                  AND monitors.is_archived = FALSE
                  AND projects.is_archived = FALSE
                """,
                (token_hash,),
            )
            monitor = cursor.fetchone()
            if monitor is None:
                return None
            cursor.execute(
                """
                UPDATE monitors
                SET last_heartbeat_at = NOW(), updated_at = NOW()
                WHERE id = %s
                """,
                (monitor["id"],),
            )

    return create_check(
        {
            "monitor_id": monitor["id"],
            "status_code": None,
            "response_time_ms": 0,
            "succeeded": True,
            "error_message": None,
        }
    )


def rotate_heartbeat_token(monitor_id: int, token_hash: str):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                UPDATE monitors
                SET heartbeat_token_hash = %s,
                    heartbeat_token_rotated_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s AND monitor_type = 'HEARTBEAT'
                RETURNING heartbeat_token_rotated_at
                """,
                (token_hash, monitor_id),
            )
            return cursor.fetchone()


def delete_monitor(monitor_id: int):
    with connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM incidents WHERE monitor_id = %s",
                (monitor_id,),
            )
            cursor.execute(
                "DELETE FROM checks WHERE monitor_id = %s",
                (monitor_id,),
            )
            cursor.execute(
                "DELETE FROM monitors WHERE id = %s RETURNING id",
                (monitor_id,),
            )
            return cursor.fetchone() is not None


def create_project(data: dict):
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                INSERT INTO projects (name, description)
                VALUES (%s, %s)
                RETURNING *
                """,
                (data["name"], data["description"]),
            )
            project = cursor.fetchone()
            return {**project, "current_status": "PENDING", "monitor_count": 0}


def list_projects():
    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                """
                SELECT projects.*,
                       COUNT(monitors.id) FILTER (
                           WHERE monitors.is_archived = FALSE
                       )::int AS monitor_count,
                       CASE
                           WHEN COUNT(monitors.id) FILTER (
                               WHERE monitors.is_active = TRUE
                                 AND monitors.is_archived = FALSE
                           ) = 0 THEN 'PENDING'
                           WHEN BOOL_OR(monitors.current_status = 'DOWN') FILTER (
                               WHERE monitors.is_active = TRUE
                                 AND monitors.is_archived = FALSE
                           ) THEN 'DOWN'
                           WHEN BOOL_OR(monitors.current_status IN ('DEGRADED', 'RECOVERING')) FILTER (
                               WHERE monitors.is_active = TRUE
                                 AND monitors.is_archived = FALSE
                           ) THEN 'DEGRADED'
                           WHEN BOOL_AND(monitors.current_status = 'UP') FILTER (
                               WHERE monitors.is_active = TRUE
                                 AND monitors.is_archived = FALSE
                           ) THEN 'UP'
                           ELSE 'PENDING'
                       END AS current_status
                FROM projects
                LEFT JOIN monitors ON monitors.project_id = projects.id
                GROUP BY projects.id
                ORDER BY projects.id
                """
            )
            return cursor.fetchall()


def update_project(project_id: int, changes: dict):
    allowed_columns = {"name", "description", "is_archived"}
    columns = [column for column in changes if column in allowed_columns]
    assignments = ", ".join(f"{column} = %s" for column in columns)
    values = [changes[column] for column in columns]

    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                f"""
                UPDATE projects
                SET {assignments}, updated_at = NOW()
                WHERE id = %s
                RETURNING *
                """,
                (*values, project_id),
            )
            project = cursor.fetchone()
            if project is None:
                return None
            cursor.execute(
                """
                SELECT COUNT(*)::int
                FROM monitors
                WHERE project_id = %s AND is_archived = FALSE
                """,
                (project_id,),
            )
            project["monitor_count"] = cursor.fetchone()["count"]
            project["current_status"] = "PENDING"
            return project


def get_monitor_history(monitor_id: int, hours: int):
    bucket_size = {24: "5 minutes", 168: "1 hour", 720: "6 hours"}[hours]

    with connect() as connection:
        with connection.cursor(row_factory=dict_row) as cursor:
            cursor.execute(
                "SELECT * FROM monitors WHERE id = %s",
                (monitor_id,),
            )
            monitor = cursor.fetchone()
            if monitor is None:
                return None

            cursor.execute(
                """
                SELECT COUNT(*)::int AS total_checks,
                       COALESCE(ROUND(AVG(succeeded::int) * 100, 2), 0) AS success_rate,
                       COUNT(*) FILTER (WHERE succeeded = FALSE)::int AS failures,
                       ROUND(AVG(response_time_ms), 2) AS avg_response_time_ms
                FROM checks
                WHERE monitor_id = %s
                  AND checked_at >= NOW() - make_interval(hours => %s)
                """,
                (monitor_id, hours),
            )
            summary = cursor.fetchone()

            cursor.execute(
                """
                SELECT date_bin(
                           %s::interval,
                           checked_at,
                           TIMESTAMPTZ '1970-01-01 00:00:00+00'
                       ) AS bucket,
                       ROUND(AVG(succeeded::int) * 100, 2) AS availability,
                       ROUND(AVG(response_time_ms), 2) AS avg_response_time_ms,
                       COUNT(*)::int AS checks
                FROM checks
                WHERE monitor_id = %s
                  AND checked_at >= NOW() - make_interval(hours => %s)
                GROUP BY bucket
                ORDER BY bucket
                """,
                (bucket_size, monitor_id, hours),
            )
            points = cursor.fetchall()

            cursor.execute(
                """
                SELECT * FROM checks
                WHERE monitor_id = %s
                  AND checked_at >= NOW() - make_interval(hours => %s)
                ORDER BY checked_at DESC, id DESC
                LIMIT 20
                """,
                (monitor_id, hours),
            )
            recent_checks = cursor.fetchall()

            cursor.execute(
                """
                SELECT * FROM incidents
                WHERE monitor_id = %s
                  AND (
                    started_at >= NOW() - make_interval(hours => %s)
                    OR resolved_at IS NULL
                    OR resolved_at >= NOW() - make_interval(hours => %s)
                  )
                ORDER BY started_at DESC, id DESC
                """,
                (monitor_id, hours, hours),
            )
            incidents = cursor.fetchall()

    if monitor["monitor_type"] == "HEARTBEAT":
        summary["avg_response_time_ms"] = None
        for point in points:
            point["avg_response_time_ms"] = None

    return {
        "monitor": monitor,
        "summary": summary,
        "points": points,
        "recent_checks": recent_checks,
        "incidents": incidents,
    }
