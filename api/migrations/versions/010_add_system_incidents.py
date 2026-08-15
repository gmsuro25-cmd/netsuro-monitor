"""Track internal component states and incidents.

Revision ID: 010
Revises: 009
"""

from alembic import op
import sqlalchemy as sa


revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_component_states",
        sa.Column("component", sa.String(length=30), primary_key=True),
        sa.Column("current_status", sa.String(length=20), nullable=False, server_default="PENDING"),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("consecutive_successes", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "system_incidents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("component", sa.String(length=30), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("opening_sample_id", sa.BigInteger(), sa.ForeignKey("system_health_samples.id", ondelete="CASCADE"), nullable=False),
        sa.Column("closing_sample_id", sa.BigInteger(), sa.ForeignKey("system_health_samples.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_system_incidents_component", "system_incidents", ["component"])
    op.create_index("ix_system_incidents_started_at", "system_incidents", ["started_at"])


def downgrade():
    op.drop_index("ix_system_incidents_started_at", table_name="system_incidents")
    op.drop_index("ix_system_incidents_component", table_name="system_incidents")
    op.drop_table("system_incidents")
    op.drop_table("system_component_states")
