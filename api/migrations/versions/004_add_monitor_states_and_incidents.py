"""Add monitor states and incidents.

Revision ID: 004
Revises: 003
"""

from alembic import op
import sqlalchemy as sa


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitors",
        sa.Column(
            "current_status",
            sa.Text(),
            nullable=False,
            server_default="PENDING",
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "monitors",
        sa.Column(
            "consecutive_successes",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_check_constraint(
        "ck_monitors_current_status",
        "monitors",
        "current_status IN ('PENDING', 'UP', 'DEGRADED', 'DOWN', 'RECOVERING')",
    )
    op.create_check_constraint(
        "ck_monitors_failure_count",
        "monitors",
        "consecutive_failures >= 0",
    )
    op.create_check_constraint(
        "ck_monitors_success_count",
        "monitors",
        "consecutive_successes >= 0",
    )

    op.create_table(
        "incidents",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column(
            "monitor_id",
            sa.BigInteger(),
            sa.ForeignKey("monitors.id"),
            nullable=False,
        ),
        sa.Column(
            "started_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "opening_check_id",
            sa.BigInteger(),
            sa.ForeignKey("checks.id"),
            nullable=False,
        ),
        sa.Column(
            "closing_check_id",
            sa.BigInteger(),
            sa.ForeignKey("checks.id"),
            nullable=True,
        ),
    )
    op.create_index(
        "uq_incidents_one_open_per_monitor",
        "incidents",
        ["monitor_id"],
        unique=True,
        postgresql_where=sa.text("resolved_at IS NULL"),
    )


def downgrade():
    op.drop_index("uq_incidents_one_open_per_monitor", table_name="incidents")
    op.drop_table("incidents")
    op.drop_constraint("ck_monitors_success_count", "monitors", type_="check")
    op.drop_constraint("ck_monitors_failure_count", "monitors", type_="check")
    op.drop_constraint("ck_monitors_current_status", "monitors", type_="check")
    op.drop_column("monitors", "consecutive_successes")
    op.drop_column("monitors", "consecutive_failures")
    op.drop_column("monitors", "current_status")
