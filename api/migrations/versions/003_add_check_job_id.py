"""Add an idempotency key to checks.

Revision ID: 003
Revises: 002
"""

from alembic import op
import sqlalchemy as sa


revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "checks",
        sa.Column("job_id", sa.Text(), nullable=True),
    )
    op.create_unique_constraint(
        "uq_checks_job_id",
        "checks",
        ["job_id"],
    )


def downgrade():
    op.drop_constraint("uq_checks_job_id", "checks", type_="unique")
    op.drop_column("checks", "job_id")
