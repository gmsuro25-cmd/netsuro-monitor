"""Add projects and assign existing monitors.

Revision ID: 006
Revises: 005
"""

from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "projects",
        sa.Column("id", sa.BigInteger(), sa.Identity(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_archived", sa.Boolean(), nullable=False, server_default=sa.false()),
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
    )

    op.add_column(
        "monitors",
        sa.Column("project_id", sa.BigInteger(), nullable=True),
    )

    connection = op.get_bind()
    laboratory_id = connection.execute(
        sa.text(
            """
            INSERT INTO projects (name, description)
            VALUES ('Laboratorio', 'Monitores creados durante el desarrollo inicial')
            RETURNING id
            """
        )
    ).scalar_one()
    connection.execute(
        sa.text("UPDATE monitors SET project_id = :project_id"),
        {"project_id": laboratory_id},
    )

    op.alter_column("monitors", "project_id", nullable=False)
    op.create_foreign_key(
        "fk_monitors_project_id",
        "monitors",
        "projects",
        ["project_id"],
        ["id"],
    )
    op.create_index("ix_monitors_project_id", "monitors", ["project_id"])


def downgrade():
    op.drop_index("ix_monitors_project_id", table_name="monitors")
    op.drop_constraint("fk_monitors_project_id", "monitors", type_="foreignkey")
    op.drop_column("monitors", "project_id")
    op.drop_table("projects")
