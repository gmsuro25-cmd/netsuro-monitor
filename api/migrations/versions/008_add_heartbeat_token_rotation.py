"""Track heartbeat token rotation.

Revision ID: 008
Revises: 007
"""

from alembic import op
import sqlalchemy as sa


revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "monitors",
        sa.Column(
            "heartbeat_token_rotated_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.execute(
        """
        UPDATE monitors
        SET heartbeat_token_rotated_at = NOW()
        WHERE heartbeat_token_hash IS NOT NULL
        """
    )


def downgrade():
    op.drop_column("monitors", "heartbeat_token_rotated_at")
