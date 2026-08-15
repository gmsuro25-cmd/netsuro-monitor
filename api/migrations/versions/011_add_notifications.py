"""Add durable notification outbox.

Revision ID: 011
Revises: 010
"""

from alembic import op
import sqlalchemy as sa


revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("event_key", sa.String(length=120), nullable=False, unique=True),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("source_id", sa.BigInteger(), nullable=False),
        sa.Column("event_type", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_status_next_attempt", "notifications", ["status", "next_attempt_at"])
    op.execute(
        """
        INSERT INTO notifications (event_key, source_type, source_id, event_type)
        SELECT 'system-' || id || '-OPENED', 'SYSTEM_INCIDENT', id, 'OPENED'
        FROM system_incidents
        WHERE resolved_at IS NULL
        ON CONFLICT (event_key) DO NOTHING
        """
    )


def downgrade():
    op.drop_index("ix_notifications_status_next_attempt", table_name="notifications")
    op.drop_table("notifications")
