"""Add Slack delivery attempt history.

Revision ID: 015
Revises: 014
"""

from alembic import op
import sqlalchemy as sa


revision = "015"
down_revision = "014"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "notification_delivery_attempts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column(
            "notification_id",
            sa.BigInteger(),
            sa.ForeignKey("notifications.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column(
            "attempted_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_notification_delivery_attempts_attempted_at",
        "notification_delivery_attempts",
        ["attempted_at"],
    )
    # Earlier transient attempts only existed in container logs. Preserve the
    # terminal failures that are still available in the outbox.
    op.execute(
        """
        INSERT INTO notification_delivery_attempts (
            notification_id, succeeded, error_message, attempted_at
        )
        SELECT id, FALSE, last_error, next_attempt_at
        FROM notifications
        WHERE status = 'FAILED' AND last_error IS NOT NULL
        """
    )
    op.execute(
        """
        INSERT INTO notification_delivery_attempts (
            notification_id, succeeded, attempted_at
        )
        SELECT id, TRUE, sent_at
        FROM notifications
        WHERE status = 'SENT' AND sent_at IS NOT NULL
        """
    )


def downgrade():
    op.drop_index(
        "ix_notification_delivery_attempts_attempted_at",
        table_name="notification_delivery_attempts",
    )
    op.drop_table("notification_delivery_attempts")
