"""Create monitors table.

Revision ID: 001
Revises: None
"""

from alembic import op
import sqlalchemy as sa


revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "monitors",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False, server_default="300"),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("expected_status_code", sa.Integer(), nullable=False, server_default="200"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint("interval_seconds >= 30", name="ck_monitors_interval"),
        sa.CheckConstraint(
            "timeout_seconds BETWEEN 1 AND 60",
            name="ck_monitors_timeout",
        ),
        sa.CheckConstraint(
            "expected_status_code BETWEEN 100 AND 599",
            name="ck_monitors_expected_status",
        ),
    )


def downgrade():
    op.drop_table("monitors")
