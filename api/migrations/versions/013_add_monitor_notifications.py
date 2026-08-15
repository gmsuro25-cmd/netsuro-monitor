"""Backfill notifications for open monitor incidents.

Revision ID: 013
Revises: 012
"""

from alembic import op


revision = "013"
down_revision = "012"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        INSERT INTO notifications (event_key, source_type, source_id, event_type)
        SELECT 'monitor-' || id || '-OPENED', 'MONITOR_INCIDENT', id, 'OPENED'
        FROM incidents
        WHERE resolved_at IS NULL
        ON CONFLICT (event_key) DO NOTHING
        """
    )


def downgrade():
    op.execute("DELETE FROM notifications WHERE source_type = 'MONITOR_INCIDENT'")
