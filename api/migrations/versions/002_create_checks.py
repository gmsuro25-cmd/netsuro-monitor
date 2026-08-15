"""Create checks table.

Revision ID: 002
Revises: 001
"""

from alembic import op
import sqlalchemy as sa


revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "checks",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "monitor_id",
            sa.BigInteger(),
            sa.ForeignKey("monitors.id"),
            nullable=False,
        ),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_time_ms", sa.Integer(), nullable=False),
        sa.Column("succeeded", sa.Boolean(), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "checked_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "status_code IS NULL OR status_code BETWEEN 100 AND 599",
            name="ck_checks_status_code",
        ),
        sa.CheckConstraint(
            "response_time_ms >= 0",
            name="ck_checks_response_time",
        ),
    )
    op.create_index(
        "ix_checks_monitor_checked_at",
        "checks",
        ["monitor_id", "checked_at"],
    )


def downgrade():
    op.drop_index("ix_checks_monitor_checked_at", table_name="checks")
    op.drop_table("checks")
