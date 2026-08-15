"""Translate application-generated stored content to English.

Revision ID: 012
Revises: 011
"""

from alembic import op


revision = "012"
down_revision = "011"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        UPDATE projects
        SET name = 'Laboratory',
            description = 'Monitors created during initial development'
        WHERE name = 'Laboratorio'
          AND description = 'Monitores creados durante el desarrollo inicial'
        """
    )
    op.execute(
        """
        UPDATE system_health_samples
        SET detail = CASE
            WHEN detail LIKE 'Respuesta en %' THEN
                'Response in ' || substring(detail FROM length('Respuesta en ') + 1)
            WHEN detail = 'Scheduler activo' THEN 'Scheduler active'
            WHEN detail = 'Señal reciente del worker' THEN 'Recent worker signal'
            WHEN detail = 'Sin señal reciente del worker' THEN 'No recent worker signal'
            WHEN detail LIKE '% en cola · % en proceso' THEN
                replace(replace(detail, ' en cola · ', ' queued · '), ' en proceso', ' processing')
            ELSE detail
        END
        WHERE detail LIKE 'Respuesta en %'
           OR detail = 'Scheduler activo'
           OR detail = 'Señal reciente del worker'
           OR detail = 'Sin señal reciente del worker'
           OR detail LIKE '% en cola · % en proceso'
        """
    )


def downgrade():
    # Stored display text is intentionally not translated back.
    pass
