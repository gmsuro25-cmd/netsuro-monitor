"""Store internal component health history.

Revision ID: 009
Revises: 008
"""

from alembic import op
import sqlalchemy as sa


revision = "009"
down_revision = "008"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_health_samples",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("component", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("response_time_ms", sa.Float(), nullable=True),
        sa.Column("stream_jobs", sa.Integer(), nullable=True),
        sa.Column("pending_jobs", sa.Integer(), nullable=True),
        sa.Column("detail", sa.String(length=500), nullable=False, server_default=""),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_system_health_component_checked_at",
        "system_health_samples",
        ["component", "checked_at"],
    )


def downgrade():
    op.drop_index("ix_system_health_component_checked_at", table_name="system_health_samples")
    op.drop_table("system_health_samples")
