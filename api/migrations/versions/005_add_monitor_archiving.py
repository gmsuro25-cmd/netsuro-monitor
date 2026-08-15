"""Add monitor archiving.

Revision ID: 005
Revises: 004
"""

from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitors",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade():
    op.drop_column("monitors", "is_archived")
