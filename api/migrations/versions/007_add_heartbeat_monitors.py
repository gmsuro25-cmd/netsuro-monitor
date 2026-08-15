"""Add heartbeat monitor support.

Revision ID: 007
Revises: 006
"""

from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitors",
        sa.Column("monitor_type", sa.Text(), nullable=False, server_default="HTTP"),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "heartbeat_grace_seconds",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )
    op.add_column(
        "monitors",
        sa.Column("heartbeat_token_hash", sa.Text(), nullable=True),
    )
    op.add_column(
        "monitors",
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.alter_column("monitors", "url", nullable=True)
    op.create_check_constraint(
        "ck_monitors_type",
        "monitors",
        "monitor_type IN ('HTTP', 'HEARTBEAT')",
    )
    op.create_check_constraint(
        "ck_monitors_heartbeat_grace",
        "monitors",
        "heartbeat_grace_seconds BETWEEN 0 AND 3600",
    )
    op.create_unique_constraint(
        "uq_monitors_heartbeat_token_hash",
        "monitors",
        ["heartbeat_token_hash"],
    )


def downgrade():
    op.drop_constraint("uq_monitors_heartbeat_token_hash", "monitors", type_="unique")
    op.drop_constraint("ck_monitors_heartbeat_grace", "monitors", type_="check")
    op.drop_constraint("ck_monitors_type", "monitors", type_="check")
    op.alter_column("monitors", "url", nullable=False)
    op.drop_column("monitors", "last_heartbeat_at")
    op.drop_column("monitors", "heartbeat_token_hash")
    op.drop_column("monitors", "heartbeat_grace_seconds")
    op.drop_column("monitors", "monitor_type")
